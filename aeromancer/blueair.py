"""Polls a Blueair purifier through Blueair's cloud and stores what its sensors saw.

Covers the Classic i-series (280i, 480i, 680i, ...), which talk to Blueair's
legacy "homehost" API. The purifier uploads a reading about every 5 minutes.
Asked for the last 0 seconds, the cloud returns that latest upload as is,
with its real time, so every 5 minutes we store it if it is new. Asked for
a longer window, it returns averages over 5-minute buckets laid on a grid
that ends at the latest upload and starts ``seconds_ago`` before it, each
stamped with its bucket's start; after a gap we fill in from those, up to a
day back, restamped with the bucket's end. Points go into the same table as
the CO2 meter's, as ``blueair_<sensor>`` (e.g. ``blueair_pm25``), plus the
fan speed and whether it is in auto mode (1 or 0) at the newest upload.

Needs the optional ``blueair_api`` package (``pip install '.[blueair]'``)
and the Blueair app login in ``~/.config/aeromancer/blueair.toml``::

    username = "you@example.com"
    password = "secret"
    device = "Bedroom"  # optional: purifier name or uuid, default the first
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import threading
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .device import Reading
from .store import Store

log = logging.getLogger(__name__)
# Its debug log prints request headers, auth token included.
logging.getLogger("blueair_api").setLevel(logging.INFO)

PREFIX = "blueair_"
POLL_SECONDS = 300.0
SAMPLE_PERIOD = 300  # seconds; the finest the cloud offers, and about how often the purifier uploads
MAX_BACKFILL = 86400  # seconds

# Column names in the cloud's datapoint table -> our quantity suffixes.
# Columns not listed here are stored under their own name.
SENSORS = {
    "pm": "pm25",
    "pm1": "pm1",
    "pm10": "pm10",
    "tmp": "temperature",
    "hum": "humidity",
    "co2": "co2",
    "voc": "voc",
    "allpollu": "all_pollution",
}


class Unavailable(Exception):
    """The optional ``blueair_api`` package is not installed."""


@dataclass
class Config:
    username: str
    password: str
    device: str | None = None  # name or uuid; None picks the first purifier


def default_config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"))
    return base / "aeromancer" / "blueair.toml"


def load_config(path: str | os.PathLike) -> Config | None:
    """The purifier's settings, or None when there is no config file."""
    path = Path(path)
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return None
    if path.stat().st_mode & 0o077:
        log.warning("%s holds a password but others can read it; chmod 600 it", path)
    try:
        config = Config(data["username"], data["password"], data.get("device"))
    except KeyError as e:
        raise ValueError(f"{path} lacks {e.args[0]!r}") from None
    if not all(isinstance(v, str) for v in (config.username, config.password, config.device or "")):
        raise ValueError(f"{path}: username, password and device must be strings")
    return config


def check_installed() -> None:
    try:
        import blueair_api  # noqa: F401
    except ImportError as e:
        raise Unavailable("the purifier needs blueair_api: pip install '.[blueair]'") from e


def parse_datapoints(data) -> list[Reading]:
    """``{"sensors": ["time", "pm", ...], "datapoints": [[ts, v, ...], ...]}`` -> readings."""
    if not isinstance(data, dict) or "sensors" not in data or "datapoints" not in data:
        raise ValueError(f"unexpected datapoint response: {str(data)[:200]}")
    sensors = data["sensors"]
    t = sensors.index("time")
    return [
        Reading(float(row[t]), PREFIX + SENSORS.get(name, name), float(value))
        for row in data["datapoints"]
        for name, value in zip(sensors, row)
        if name != "time" and isinstance(value, (int, float))
    ]


def pick(devices: list[dict], wanted: str | None) -> tuple[str, str]:
    """``(uuid, name)`` of the purifier named or numbered ``wanted``, or of the first one."""
    for d in devices:
        if wanted in (None, d["uuid"], d["name"]):
            if wanted is None and len(devices) > 1:
                log.info("the account has %d purifiers; using %r (choose with 'device' in the config)", len(devices), d["name"])
            return d["uuid"], d["name"]
    names = ", ".join(repr(d["name"]) for d in devices) or "none"
    raise LookupError(f"no Blueair purifier {wanted!r} on the account (it has: {names})")


async def poll_once(api, uuid: str, store: Store, since: float) -> float:
    """Store the uploads after ``since``; return the time of the newest one stored."""
    readings = parse_datapoints(await api.get_data_points_since(uuid, seconds_ago=0, sample_period=SAMPLE_PERIOD))
    newest = max((r.ts for r in readings), default=since)
    if newest <= since:
        return since
    gap = newest - since
    if gap > 1.5 * SAMPLE_PERIOD:  # missed uploads: fill in from the 5-minute averages
        seconds_ago = SAMPLE_PERIOD * math.ceil(min(gap, MAX_BACKFILL) / SAMPLE_PERIOD)
        averages = await api.get_data_points_since(uuid, seconds_ago=seconds_ago, sample_period=SAMPLE_PERIOD)
        for r in parse_datapoints(averages):
            end = r.ts + SAMPLE_PERIOD
            if since + SAMPLE_PERIOD / 2 < end < newest:
                readings.append(Reading(end, r.quantity, r.value))
    attributes = await api.get_attributes(uuid)
    if "fan_speed" in attributes:
        readings.append(Reading(newest, PREFIX + "fan_speed", float(attributes["fan_speed"])))
    if "mode" in attributes:  # "auto": the fan follows the sensor named by auto_mode_dependency ("pm"), else it is set by hand
        readings.append(Reading(newest, PREFIX + "auto_mode", float(attributes["mode"] == "auto")))
    store.add(readings)
    log.debug("stored %d Blueair readings up to %s", len(readings), time.ctime(newest))
    return newest


async def _sleep(stop: threading.Event, seconds: float) -> None:
    end = time.monotonic() + seconds
    while not stop.is_set() and time.monotonic() < end:
        await asyncio.sleep(1)


async def _poll(db_path, config: Config, stop: threading.Event) -> None:
    from blueair_api import HttpBlueair

    store = Store(db_path)
    since = store.last_ts(PREFIX + "*") or 0.0
    api = None
    try:
        while not stop.is_set():
            try:
                if api is None:
                    api = HttpBlueair(username=config.username, password=config.password)
                    uuid, name = pick(await api.get_devices(), config.device)
                    log.info("polling Blueair %r into %s", name, db_path)
                since = await poll_once(api, uuid, store, since)
            except Exception as e:  # network, expired token, odd response: log in again next time
                log.warning("Blueair: %s; retrying in %.0f s", e or type(e).__name__, POLL_SECONDS)
                if api is not None:
                    await api.cleanup_client_session()
                    api = None
            await _sleep(stop, POLL_SECONDS)
    finally:
        if api is not None:
            await api.cleanup_client_session()
        store.close()


def poll(db_path, config: Config, stop: threading.Event | None = None) -> None:
    """Poll until ``stop`` is set, logging in again after any failure."""
    asyncio.run(_poll(db_path, config, stop or threading.Event()))


def start_in_background(db_path, config: Config) -> threading.Event:
    stop = threading.Event()
    threading.Thread(
        target=poll,
        args=(db_path, config, stop),
        name="blueair",
        daemon=True,
    ).start()
    return stop
