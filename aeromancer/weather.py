"""Polls Singapore's weather stations near home and stores them next to the indoor readings.

NEA publishes through data.gov.sg what its stations measure: air
temperature, relative humidity, wind speed and direction every minute from
about 18 stations, and 5-minute rainfall totals from about 90. For each of
these we store the ``NEAREST`` stations to home, as
``nea_<kind>_<station>`` (e.g. ``nea_temperature_S109``), one point per 5
minutes, and keep each station's name and position in the ``stations``
table, so the station that best stands for home can be chosen later.
Averages and totals are stamped at the middle of their window, assuming
the API stamps the window's end, as it does for PM2.5
(docs/outdoor-pm25.md).

Asked with ``?date=YYYY-MM-DD``, the API returns that day's readings newest
first, 25 timestamps a page, so the same walk back through the pages takes
the latest readings and fills in any gap, up to a day back. Free, and
works without an API key.

Polls when ``~/.config/aeromancer/nea.toml`` gives home's position, which
stays there, out of the repository and off the public dashboard::

    latitude = 1.35  # two decimals (about 1 km) are plenty
    longitude = 103.85
"""

from __future__ import annotations

import datetime as dt
import logging
import math
import os
import threading
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import nea
from .device import Reading
from .store import Store

log = logging.getLogger(__name__)

URL = "https://api-open.data.gov.sg/v2/real-time/api/"
PREFIX = "nea_"
NEAREST = 3
STEP = 300  # seconds between stored points
POLL_SECONDS = 300.0
LATE = 600  # seconds: re-read this far before the newest stored point; late stations were seen to report within 5 minutes
MAX_BACKFILL = 86400  # seconds
PAUSE = 5.0  # seconds between requests; data.gov.sg answers bursts with 429 Too Many Requests


@dataclass(frozen=True)
class Kind:
    endpoint: str
    name: str  # quantity: nea_<name>_<station>
    unit: str  # readingUnit as the API states it
    scale: float  # to our unit
    window: float  # seconds the value averages or totals over, ending at its timestamp


KNOTS = 1852 / 3600  # m/s
KINDS = (
    Kind("air-temperature", "temperature", "deg C", 1, 0),
    Kind("relative-humidity", "humidity", "percentage", 1, 0),
    Kind("rainfall", "rain", "mm", 1, 300),  # mm in 5 minutes
    Kind("wind-speed", "wind_speed", "knots", KNOTS, 600),  # m/s
    Kind("wind-direction", "wind_direction", "degrees", 1, 600),  # where it blows from, degrees from north
)


def load_home(path: str | os.PathLike) -> tuple[float, float] | None:
    """Home's ``(latitude, longitude)``, or None when the config file has none."""
    try:
        with Path(path).open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return None
    if "latitude" not in data and "longitude" not in data:
        return None
    lat, lon = data.get("latitude"), data.get("longitude")
    if not all(isinstance(v, (int, float)) for v in (lat, lon)) or not (1.1 < lat < 1.5 and 103.5 < lon < 104.1):
        raise ValueError(f"{path}: latitude and longitude must be numbers in Singapore, not {lat!r}, {lon!r}")
    return float(lat), float(lon)


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Kilometres; flat Earth is fine across Singapore."""
    dy = b[0] - a[0]
    dx = (b[1] - a[1]) * math.cos(math.radians(a[0]))
    return 111.2 * math.hypot(dx, dy)


def nearest(stations: list[dict], home: tuple[float, float], n: int = NEAREST) -> list[dict]:
    def km(s):
        return distance(home, (s["location"]["latitude"], s["location"]["longitude"]))

    return sorted(stations, key=km)[:n]


def home_series(store: Store, home, name: str, start: float, end: float, bucket: float) -> list:
    """``Store.series`` of the nearest station with ``nea_<name>`` readings in the window, or []."""
    if home is None:
        return []
    for station in sorted(store.stations().items(), key=lambda kv: distance(home, kv[1])):
        rows = store.series(f"{PREFIX}{name}_{station[0]}", start, end, bucket)
        if rows:
            return rows
    return []


def fetch(kind: Kind, date: dt.date, token: str | None = None) -> dict:
    url = f"{URL}{kind.endpoint}?date={date.isoformat()}" + (f"&paginationToken={token}" if token else "")
    return nea.fetch_json(url) or {"code": 0, "data": {"readings": []}}


def _time(timestamp: str) -> float:
    return dt.datetime.fromisoformat(timestamp).timestamp()


def check(kind: Kind, data) -> dict:
    """The response's ``data``, after checking that it is what we expect."""
    if not isinstance(data, dict) or data.get("code") != 0 or not isinstance(data.get("data"), dict):
        raise ValueError(f"unexpected {kind.endpoint} response: {str(data)[:200]}")
    data = data["data"]
    if data.get("readings") and data.get("readingUnit") != kind.unit:
        raise ValueError(f"{kind.endpoint} now comes in {data.get('readingUnit')!r}, not {kind.unit!r}")
    return data


def parse(kind: Kind, data: dict, stations: set[str]) -> list[Reading]:
    """The ``stations``' readings on the 5-minute grid, each stamped at the middle of its window."""
    return [
        Reading(t - kind.window / 2, f"{PREFIX}{kind.name}_{d['stationId']}", float(d["value"]) * kind.scale)
        for item in data["readings"]
        if (t := _time(item["timestamp"])) % STEP == 0
        for d in item["data"]
        if d["stationId"] in stations and isinstance(d["value"], (int, float))
    ]


def poll_kind(store: Store, kind: Kind, home, now: float | None = None, get=None, pause: float = PAUSE) -> int:
    """Store the nearest stations' readings that are new; return how many."""
    now = time.time() if now is None else now
    get = get or fetch
    day = dt.datetime.fromtimestamp(now, nea.SINGAPORE).date()
    data = check(kind, get(kind, day))
    if not data.get("readings"):  # just after midnight: nothing yet today
        day -= dt.timedelta(days=1)
        time.sleep(pause)
        data = check(kind, get(kind, day))
    near = nearest(data.get("stations") or [], home)
    if not near:
        raise ValueError(f"no {kind.endpoint} stations listed")
    ids = {s["id"] for s in near}
    newest = {i: store.last_ts(f"{PREFIX}{kind.name}_{i}") or 0.0 for i in ids}
    since = max(max(newest.values()) - LATE, now - MAX_BACKFILL)

    readings = []
    while True:
        readings += parse(kind, data, ids)
        items, token = data["readings"], data.get("paginationToken")
        if items and _time(items[-1]["timestamp"]) <= since:
            break
        if not (items and token):  # this day is done: go on with the one before, if the gap reaches it
            if dt.datetime.combine(day, dt.time(), nea.SINGAPORE).timestamp() <= since:
                break
            day -= dt.timedelta(days=1)
            token = None
        time.sleep(pause)
        data = check(kind, get(kind, day, token))

    oldest = now - MAX_BACKFILL
    readings = [r for r in readings if r.ts > max(oldest, newest[r.quantity.rsplit("_", 1)[1]])]
    store.add(readings)
    store.add_stations((s["id"], s["name"], s["location"]["latitude"], s["location"]["longitude"]) for s in near)
    return len(readings)


def poll_once(store: Store, home, now: float | None = None, get=None, pause: float = PAUSE) -> None:
    for i, kind in enumerate(KINDS):
        if i:
            time.sleep(pause)
        n = poll_kind(store, kind, home, now, get, pause)
        log.debug("stored %d NEA %s readings", n, kind.name)


def poll(db_path, home: tuple[float, float], stop: threading.Event | None = None) -> None:
    """Poll until ``stop`` is set, retrying after any failure."""
    stop = stop or threading.Event()
    store = Store(db_path)
    log.info("polling NEA weather stations into %s", db_path)
    try:
        while not stop.is_set():
            try:
                poll_once(store, home)
            except Exception as e:  # network, rate limit, odd response: try again next time
                log.warning("NEA weather: %s; retrying in %.0f s", e or type(e).__name__, POLL_SECONDS)
            stop.wait(POLL_SECONDS)
    finally:
        store.close()


def start_in_background(db_path, home: tuple[float, float]) -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=poll, args=(db_path, home, stop), name="weather", daemon=True).start()
    return stop
