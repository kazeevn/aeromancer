"""Polls Singapore's official outdoor PM2.5 and stores it next to the indoor readings.

NEA, the National Environment Agency, publishes through data.gov.sg the mean
PM2.5 over the past hour for five regions (north, south, east, west, central),
every hour, stamped with the hour's end. We store each at the middle of its
hour (see docs/nea.md), all five in the table as
``nea_pm25_<region>``, so the region a home best matches can be chosen
later. Asked with ``?date=YYYY-MM-DD``, the API returns that whole day, which
fills in any gap up to a week back. Free, and works without an API key.

Polls when ``~/.config/aeromancer/nea.toml`` names the home region, the one
the dashboard charts. It lives there, not on the command line, so that it
stays out of the repository and off the public dashboard::

    region = "central"
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import threading
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from .device import Reading
from .store import Store

log = logging.getLogger(__name__)

URL = "https://api-open.data.gov.sg/v2/real-time/api/pm25"
PREFIX = "nea_pm25_"
REGIONS = ("north", "south", "east", "west", "central")
SINGAPORE = dt.timezone(dt.timedelta(hours=8))
POLL_SECONDS = 600.0  # readings come hourly; this catches each within 10 minutes
PERIOD = 3600
MAX_BACKFILL = 7 * 86400  # seconds
BACKFILL_PAUSE = 5.0  # seconds between the days of a backfill


def default_config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"))
    return base / "aeromancer" / "nea.toml"


def load_region(path: str | os.PathLike) -> str | None:
    """The home region, or None when the config file names none."""
    try:
        with Path(path).open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return None
    if "region" not in data:  # it may give only home's position, for the weather
        return None
    region = data["region"]
    if region not in REGIONS:
        raise ValueError(f"{path}: region must be one of {', '.join(REGIONS)}, not {region!r}")
    return region


def fetch_json(url: str) -> dict | None:
    """A data.gov.sg response, or None for 404, which it answers for a day with no readings yet."""
    request = urllib.request.Request(url, headers={"User-Agent": "aeromancer"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def fetch(date: dt.date | None = None) -> dict:
    """The latest reading, or every reading of ``date`` (Singapore time)."""
    url = URL if date is None else f"{URL}?date={date.isoformat()}"
    return fetch_json(url) or {"code": 0, "data": {"items": []}}


def parse(data) -> list[Reading]:
    """``{"code": 0, "data": {"items": [{"timestamp": ..., "readings": {"pm25_one_hourly": {...}}}]}}`` -> readings.

    Each is stamped half an hour before its ``timestamp``: the middle of the hour it averages.
    """
    if not isinstance(data, dict) or data.get("code") != 0 or not isinstance(data.get("data"), dict):
        raise ValueError(f"unexpected PM2.5 response: {str(data)[:200]}")
    return [
        Reading(dt.datetime.fromisoformat(item["timestamp"]).timestamp() - PERIOD / 2, PREFIX + region, float(value))
        for item in data["data"]["items"]
        for region, value in item["readings"]["pm25_one_hourly"].items()
        if isinstance(value, (int, float))
    ]


def poll_once(store: Store, since: float, now: float | None = None, get=None, pause: float | None = None) -> float:
    """Store the readings after ``since``; return the time of the newest one stored.

    After a gap, fetches whole days from the gap's start to today, oldest
    first, storing each as it comes, so a failure keeps the days before it.
    """
    now = time.time() if now is None else now
    get = get or fetch
    pause = BACKFILL_PAUSE if pause is None else pause
    if now - since <= 2 * PERIOD:
        return _store_after(store, parse(get()), since)
    day = dt.datetime.fromtimestamp(max(since, now - MAX_BACKFILL), SINGAPORE).date()
    today = dt.datetime.fromtimestamp(now, SINGAPORE).date()
    while day <= today:
        since = _store_after(store, parse(get(day)), since)
        day += dt.timedelta(days=1)
        if day <= today:
            time.sleep(pause)  # data.gov.sg answers bursts with 429 Too Many Requests
    return since


def _store_after(store: Store, readings: list[Reading], since: float) -> float:
    readings = [r for r in readings if r.ts > since]
    if not readings:
        return since
    store.add(readings)
    newest = max(r.ts for r in readings)
    log.debug("stored %d NEA PM2.5 readings up to %s", len(readings), time.ctime(newest))
    return newest


def poll(db_path, stop: threading.Event | None = None) -> None:
    """Poll until ``stop`` is set, retrying after any failure."""
    stop = stop or threading.Event()
    store = Store(db_path)
    restamp_hour_ends(store)
    log.info("polling NEA outdoor PM2.5 into %s", db_path)
    try:
        while not stop.is_set():
            try:
                # From the table, not the last return value: a failed backfill may have stored some days.
                poll_once(store, store.last_ts(PREFIX + "*") or 0.0)
            except Exception as e:  # network, rate limit, odd response: try again next time
                log.warning("NEA: %s; retrying in %.0f s", e or type(e).__name__, POLL_SECONDS)
            stop.wait(POLL_SECONDS)
    finally:
        store.close()


def restamp_hour_ends(store: Store) -> None:
    """Move readings stored at their hour's end, as the first version did, to its middle."""
    with store.db:
        moved = store.db.execute(
            "UPDATE readings SET ts = ts - ? WHERE quantity GLOB ? AND CAST(ts AS INTEGER) % ? = 0",
            (PERIOD / 2, PREFIX + "*", PERIOD),
        ).rowcount
    if moved:
        log.info("moved %d NEA readings from their hour's end to its middle", moved)


def start_in_background(db_path) -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=poll, args=(db_path, stop), name="nea", daemon=True).start()
    return stop
