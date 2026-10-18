"""Polls the air pressure that the airports around Singapore report, and interpolates it for home.

NEA's real-time API on data.gov.sg has no pressure, so this takes what the
airports send to the world's weather services, from two free sources that
need no key:

- SYNOP, through Ogimet: station-level and sea-level pressure in tenths of a
  hPa, with temperature and dew point. Changi every 3 hours, Senai (Johor)
  and Tanjung Pinang (Bintan) every hour.
- METAR, through aviationweather.gov: QNH in whole hPa, rounded down, with
  temperature and dew point in whole °C. Changi, Paya Lebar, Seletar, Senai,
  Batam and Tanjung Pinang, every 30 or 60 minutes.

Each is stored raw at its observation time, as ``synop_<field>_<WMO id>``
and ``metar_<field>_<ICAO id>``, and each airport's position and elevation go
into the ``stations`` table. A SYNOP station stands at the airport whose
METARs it shares (``SYNOP``).

For each hour, every station's report becomes a sea-level pressure, and a
plane fitted through them by weighted least squares gives
``home_pressure_msl`` at home; with the meter's altitude,
``home_pressure`` is the pressure at the meter's height (docs/pressure.md).

Polls when ``~/.config/aeromancer/nea.toml`` gives home's position (see
weather.py). The altitude is ``altitude_m`` in
``~/.config/aeromancer/zytemp.toml``, also kept out of the repository::

    altitude_m = 30  # the meter's height above mean sea level
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import os
import re
import threading
import time
import tomllib
import urllib.request
from pathlib import Path

from .device import Reading
from .store import Store

log = logging.getLogger(__name__)

SYNOP_URL = "https://www.ogimet.com/cgi-bin/getsynop"
METAR_URL = "https://aviationweather.gov/api/data/metar"
SYNOP = {"48698": "WSSS", "48679": "WMKJ", "96091": "WIDN"}  # WMO id -> ICAO id of the same airport
METAR = ("WSSS", "WSAP", "WSSL", "WMKJ", "WIDD", "WIDN")
OUTPUTS = "home_pressure*"
HOUR = 3600
ON_THE_HOUR = 600  # seconds: a report this close to an hour counts for it
POLL_SECONDS = 1800.0
LATE = 3 * HOUR  # re-read this far before the newest stored report, for stations that report late
MAX_BACKFILL = 7 * 86400  # seconds
METAR_CHUNK = 24  # hours per request: one returns at most 400 reports, and a day of these airports is about 220
PAUSE = 5.0  # seconds between requests

SYNOP_SIGMA = 0.1  # hPa: tenths
METAR_SIGMA = 0.3  # hPa: rounded down to a whole hPa, uniform over 1 hPa has a standard deviation of 0.29
GRADIENT_SIGMA = 0.005  # hPa/km: prior on each component of the gradient; tropical gradients are about 0.5 hPa per 100 km
MIN_STATIONS = 3
G = 9.80665  # m/s²
R_DRY = 287.05  # J/(kg K)


def default_altitude_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"))
    return base / "aeromancer" / "zytemp.toml"


def load_altitude(path: str | os.PathLike) -> float | None:
    """The meter's height above mean sea level in metres, or None when the config file has none."""
    try:
        with Path(path).open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return None
    if "altitude_m" not in data:
        return None
    altitude = data["altitude_m"]
    if not isinstance(altitude, (int, float)) or not -100 < altitude < 5000:
        raise ValueError(f"{path}: altitude_m must be metres above sea level, not {altitude!r}")
    return float(altitude)


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "aeromancer"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def fetch_synop(station: str, start: float, end: float) -> str:
    """Ogimet's CSV of the station's SYNOPs from ``start`` to ``end``."""
    def utc(t):
        return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y%m%d%H%M")

    return _get(f"{SYNOP_URL}?block={station}&begin={utc(start)}&end={utc(end)}").decode()


def fetch_metar(stations: tuple[str, ...], end: float, hours: int) -> list:
    """aviationweather.gov's JSON of the stations' METARs over the ``hours`` before ``end``."""
    date = dt.datetime.fromtimestamp(end, dt.timezone.utc).strftime("%Y%m%d_%H%M")
    return json.loads(_get(f"{METAR_URL}?ids={','.join(stations)}&hours={hours}&date={date}&format=json") or b"[]")


def _hpa(group: str) -> float:
    """``3PPPP`` or ``4PPPP``, tenths of a hPa without the thousands -> hPa."""
    p = int(group[1:]) / 10
    return p + 1000 if p < 500 else p


def _celsius(group: str) -> float:
    """``1sTTT`` or ``2sTTT``: sign, then tenths of a degree."""
    return (-1 if group[1] == "1" else 1) * int(group[2:]) / 10


def parse_synop(text: str) -> list[Reading]:
    """Ogimet's ``48698,2026,10,18,06,00,AAXX 18064 48698 01540 71409 10318 20247 30079 40095 ...=`` lines -> readings.

    Takes the temperature, dew point, station-level and sea-level pressure
    from section 1, whose groups come in the order of their first digit.
    """
    readings = []
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.split(",", 6)
        if len(fields) < 7 or not re.fullmatch(r"\d{5}", fields[0]) or not fields[6].startswith("AAXX"):
            raise ValueError(f"unexpected Ogimet response: {text[:200]}")
        station = fields[0]
        ts = dt.datetime(*map(int, fields[1:6]), tzinfo=dt.timezone.utc).timestamp()
        groups = fields[6].rstrip("= ").split()
        if len(groups) < 5 or groups[3] == "NIL":
            continue
        body = groups[5:]  # after AAXX, YYGGi, IIiii, iRixhVV and Nddff
        if groups[4][3:5] == "99" and body:
            body = body[1:]  # 00fff: wind of 99 knots or more
        last = 0
        for group in body:
            if not re.fullmatch(r"[1-9][0-9/]{4}", group) or int(group[0]) <= last:
                break  # 333, 555, or a malformed group: section 1 is over
            last = int(group[0])
            if "/" in group:
                continue
            if group[0] == "1" and group[1] in "01":
                readings.append(Reading(ts, f"synop_temperature_{station}", _celsius(group)))
            elif group[0] == "2" and group[1] in "01":  # 29UUU would be relative humidity
                readings.append(Reading(ts, f"synop_dewpoint_{station}", _celsius(group)))
            elif group[0] == "3":
                readings.append(Reading(ts, f"synop_pressure_{station}", _hpa(group)))
            elif group[0] == "4":
                readings.append(Reading(ts, f"synop_msl_{station}", _hpa(group)))
    return readings


def parse_metar(data) -> tuple[list[Reading], list[tuple]]:
    """aviationweather.gov's JSON -> the readings, and the stations as ``(id, name, latitude, longitude, elevation)``.

    Takes the routine METARs only: SPECIs come between the hours.
    """
    if not isinstance(data, list):
        raise ValueError(f"unexpected METAR response: {str(data)[:200]}")
    readings, stations = [], {}
    for m in data:
        qnh = re.search(r" Q(\d{4})\b", m.get("rawOb", ""))
        if m.get("metarType") != "METAR" or not qnh:
            continue
        icao, ts = m["icaoId"], float(m["obsTime"])
        readings.append(Reading(ts, f"metar_qnh_{icao}", float(qnh.group(1))))
        for field, key in (("temperature", "temp"), ("dewpoint", "dewp")):
            if isinstance(m.get(key), (int, float)):
                readings.append(Reading(ts, f"metar_{field}_{icao}", float(m[key])))
        stations[icao] = (icao, m["name"], m["lat"], m["lon"], m["elev"])
    return readings, list(stations.values())


def virtual_temperature(temperature: float, dewpoint: float, pressure: float = 1010.0) -> float:
    """Kelvin: the temperature dry air would need to be as light as this moist air."""
    vapour = 6.112 * math.exp(17.62 * dewpoint / (243.12 + dewpoint))  # hPa, Magnus formula over water
    return (temperature + 273.15) * (1 + 0.378 * vapour / pressure)


def descend(pressure: float, height: float, tv: float) -> float:
    """The pressure ``height`` metres below, through air at virtual temperature ``tv`` (hypsometric equation)."""
    return pressure * math.exp(G * height / (R_DRY * tv))


def metar_msl(qnh: float, elevation: float, tv: float) -> float:
    """Sea-level pressure from a QNH rounded down to a whole hPa.

    QNH is the station's pressure taken down to sea level through the ICAO
    standard atmosphere, 15 °C at sea level. Undo that, and take it down
    through the air as it is instead: at 30 °C, this lowers it by about
    0.008 hPa per metre of the station's elevation.
    """
    station = (qnh + 0.5) * (1 - 0.0065 * elevation / 288.15) ** 5.2559
    return descend(station, elevation, tv)


def fit_plane(points: list[tuple[float, float, float, float]]) -> float | None:
    """``(x, y, value, sigma)`` -> the plane's value at (0, 0), or None with fewer than ``MIN_STATIONS`` points.

    Weighted least squares, with a Gaussian prior of ``GRADIENT_SIGMA`` on
    the gradient (ridge regression). For most of Singapore the plane is
    extrapolated, and without the prior one QNH stepping by 1 hPa can tilt
    it by about 1 hPa at home (docs/pressure.md).
    """
    if len(points) < MIN_STATIONS:
        return None
    weights = [1 / s**2 for *_, s in points]
    total = sum(weights)

    def mean(k):
        return sum(w * p[k] for w, p in zip(weights, points)) / total

    m = [mean(k) for k in range(3)]

    def cov(i, j):
        return sum(w * (p[i] - m[i]) * (p[j] - m[j]) for w, p in zip(weights, points)) / total

    prior = 1 / (total * GRADIENT_SIGMA**2)
    sxx, syy, sxy, sxv, syv = cov(0, 0) + prior, cov(1, 1) + prior, cov(0, 1), cov(0, 2), cov(1, 2)
    det = sxx * syy - sxy**2
    bx = (syy * sxv - sxy * syv) / det
    by = (sxx * syv - sxy * sxv) / det
    return m[2] - bx * m[0] - by * m[1]


def offset(home: tuple[float, float], position: tuple[float, float]) -> tuple[float, float]:
    """Kilometres east and north from home; flat Earth, as in weather.distance."""
    return 111.2 * (position[1] - home[1]) * math.cos(math.radians(home[0])), 111.2 * (position[0] - home[0])


def interpolate(store: Store, home: tuple[float, float], altitude: float | None, start: float, end: float) -> list[Reading]:
    """``home_pressure_msl``, and ``home_pressure`` with the altitude, on each hour from ``start`` to ``end`` that enough stations reported."""
    positions, elevations = store.stations(), store.elevations()
    hours: dict[float, dict[tuple[str, str], dict[str, float]]] = {}
    for ts, quantity, value in store.rows("synop_*", start - ON_THE_HOUR, end + ON_THE_HOUR) + store.rows(
        "metar_*", start - ON_THE_HOUR, end + ON_THE_HOUR
    ):
        hour = round(ts / HOUR) * HOUR
        if abs(ts - hour) <= ON_THE_HOUR and start <= hour <= end:
            source, field, station = quantity.split("_", 2)
            hours.setdefault(hour, {}).setdefault((source, station), {})[field] = value

    out = []
    for hour, reports in sorted(hours.items()):
        points, nearest = [], None  # nearest: (km, virtual temperature)
        for (source, station), r in reports.items():
            airport = SYNOP.get(station) if source == "synop" else station
            if airport not in positions:
                continue
            x, y = offset(home, positions[airport])
            tv = virtual_temperature(r["temperature"], r["dewpoint"]) if {"temperature", "dewpoint"} <= r.keys() else None
            if tv is not None and (nearest is None or math.hypot(x, y) < nearest[0]):
                nearest = (math.hypot(x, y), tv)
            if source == "synop" and "msl" in r:
                points.append((x, y, r["msl"], SYNOP_SIGMA))
            elif source == "metar" and "qnh" in r and tv is not None and airport in elevations:
                synop = next((w for w, i in SYNOP.items() if i == station), None)
                if "msl" not in reports.get(("synop", synop), {}):  # the same barometer, in finer steps
                    points.append((x, y, metar_msl(r["qnh"], elevations[airport], tv), METAR_SIGMA))
        msl = fit_plane(points)
        if msl is None:
            continue
        out.append(Reading(hour, "home_pressure_msl", round(msl, 2)))
        if altitude is not None and nearest is not None:
            out.append(Reading(hour, "home_pressure", round(descend(msl, -altitude, nearest[1]), 2)))
    return out


def update_home(store: Store, home, altitude, start: float, end: float) -> int:
    """Recompute the hours from ``start`` to ``end``; return how many have a pressure."""
    start, end = math.ceil(start / HOUR) * HOUR, math.floor(end / HOUR) * HOUR
    readings = interpolate(store, home, altitude, start, end)
    store.replace(OUTPUTS, start, end, readings)
    return sum(r.quantity == "home_pressure_msl" for r in readings)


def _since(store: Store, pattern: str, now: float) -> float:
    return max((store.last_ts(pattern) or 0.0) - LATE, now - MAX_BACKFILL)


def poll_once(store: Store, home, altitude, now: float | None = None, get_synop=None, get_metar=None, pause: float = PAUSE) -> int:
    """Store the readings that are new and recompute the hours they touch; return how many readings."""
    now = time.time() if now is None else now
    get_synop, get_metar = get_synop or fetch_synop, get_metar or fetch_metar
    times = []
    try:  # each source is stored as it comes, so that one failing keeps the other
        readings, stations = [], {}
        since, end = _since(store, "metar_*", now), now
        while end > since:
            new, listed = parse_metar(get_metar(METAR, end, METAR_CHUNK))
            readings += new
            stations.update((s[0], s) for s in listed)
            end -= METAR_CHUNK * HOUR
            time.sleep(pause)
        store.add_stations(stations.values())  # first: interpolating needs the positions
        times += _store_new(store, readings)

        readings = []
        since = _since(store, "synop_*", now)
        for i, station in enumerate(SYNOP):
            if i:
                time.sleep(pause)
            readings += parse_synop(get_synop(station, since, now))
        times += _store_new(store, readings)
    finally:
        if times:
            update_home(store, home, altitude, min(times) - ON_THE_HOUR, max(times) + ON_THE_HOUR)
    return len(times)


def _store_new(store: Store, readings: list[Reading]) -> list[float]:
    """Store the readings newer than the newest of their quantity, each once; return their times."""
    newest = {}
    for r in readings:
        if r.quantity not in newest:
            newest[r.quantity] = store.last_ts(r.quantity) or 0.0
    new = {(r.ts, r.quantity): r for r in readings if r.ts > newest[r.quantity]}  # a report fetched twice counts once
    store.add(new.values())
    return [ts for ts, _ in new]


def poll(db_path, home: tuple[float, float], altitude: float | None, stop: threading.Event | None = None) -> None:
    """Poll until ``stop`` is set, retrying after any failure."""
    stop = stop or threading.Event()
    store = Store(db_path)
    log.info("polling the airports' air pressure into %s", db_path)
    try:
        # The altitude or the method may have changed since the hours were computed.
        first = min(filter(None, (store.first_ts("synop_*"), store.first_ts("metar_*"))), default=None)
        if first is not None:
            update_home(store, home, altitude, first - ON_THE_HOUR, time.time())
        while not stop.is_set():
            try:
                n = poll_once(store, home, altitude)
                log.debug("stored %d pressure readings", n)
            except Exception as e:  # network, rate limit, odd response: try again next time
                log.warning("pressure: %s; retrying in %.0f s", e or type(e).__name__, POLL_SECONDS)
            stop.wait(POLL_SECONDS)
    finally:
        store.close()


def start_in_background(db_path, home: tuple[float, float], altitude: float | None) -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=poll, args=(db_path, home, altitude, stop), name="pressure", daemon=True).start()
    return stop
