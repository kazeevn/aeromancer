"""Just enough real astronomy to make the pseudo-science sound authoritative.

Planet positions use the JPL "Approximate Positions of the Planets" Keplerian
elements (E. M. Standish, valid 1800-2050), good to a fraction of a degree.
The Moon uses the mean synodic month, good to about half a day.
"""

from __future__ import annotations

import math

J2000 = 2451545.0
SYNODIC_MONTH = 29.530588853  # days
REFERENCE_NEW_MOON = 2451550.26  # JD, 2000-01-06 18:14 UTC
DAY = 86400.0

ZODIAC = (
    ("Aries", "♈︎"),
    ("Taurus", "♉︎"),
    ("Gemini", "♊︎"),
    ("Cancer", "♋︎"),
    ("Leo", "♌︎"),
    ("Virgo", "♍︎"),
    ("Libra", "♎︎"),
    ("Scorpio", "♏︎"),
    ("Sagittarius", "♐︎"),
    ("Capricorn", "♑︎"),
    ("Aquarius", "♒︎"),
    ("Pisces", "♓︎"),
)

MOON_PHASES = (
    "New Moon",
    "Waxing Crescent",
    "First Quarter",
    "Waxing Gibbous",
    "Full Moon",
    "Waning Gibbous",
    "Last Quarter",
    "Waning Crescent",
)

# (a [AU], e, I [deg], L [deg], long. perihelion [deg], long. asc. node [deg]),
# then their rates per Julian century.
_ELEMENTS = {
    "mercury": (
        (0.38709927, 0.20563593, 7.00497902, 252.25032350, 77.45779628, 48.33076593),
        (0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081),
    ),
    "earth": (
        (1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0),
        (0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0.0),
    ),
}


def julian_day(ts: float) -> float:
    return ts / DAY + 2440587.5


def _heliocentric(planet: str, jd: float) -> tuple[float, float, float]:
    base, rate = _ELEMENTS[planet]
    t = (jd - J2000) / 36525
    a, e, inc, mean_long, peri, node = (b + r * t for b, r in zip(base, rate))
    m = math.radians((mean_long - peri) % 360)
    w = math.radians(peri - node)
    node = math.radians(node)
    inc = math.radians(inc)

    ecc_anomaly = m + e * math.sin(m)
    for _ in range(8):
        ecc_anomaly -= (ecc_anomaly - e * math.sin(ecc_anomaly) - m) / (1 - e * math.cos(ecc_anomaly))
    xp = a * (math.cos(ecc_anomaly) - e)
    yp = a * math.sqrt(1 - e * e) * math.sin(ecc_anomaly)

    cw, sw = math.cos(w), math.sin(w)
    cn, sn = math.cos(node), math.sin(node)
    ci, si = math.cos(inc), math.sin(inc)
    x = (cw * cn - sw * sn * ci) * xp + (-sw * cn - cw * sn * ci) * yp
    y = (cw * sn + sw * cn * ci) * xp + (-sw * sn + cw * cn * ci) * yp
    z = (sw * si) * xp + (cw * si) * yp
    return x, y, z


def mercury_longitude(ts: float) -> float:
    """Geocentric ecliptic longitude of Mercury, degrees."""
    jd = julian_day(ts)
    mx, my, _ = _heliocentric("mercury", jd)
    ex, ey, _ = _heliocentric("earth", jd)
    return math.degrees(math.atan2(my - ey, mx - ex)) % 360


def sun_longitude(ts: float) -> float:
    ex, ey, _ = _heliocentric("earth", julian_day(ts))
    return math.degrees(math.atan2(-ey, -ex)) % 360


def mercury_motion(ts: float) -> float:
    """Apparent motion of Mercury in degrees per day; negative means retrograde."""
    half = DAY / 2
    return (mercury_longitude(ts + half) - mercury_longitude(ts - half) + 540) % 360 - 180


def mercury_is_retrograde(ts: float) -> bool:
    return mercury_motion(ts) < 0


def _station_between(a: float, b: float) -> float:
    retro_a = mercury_is_retrograde(a)
    for _ in range(30):
        mid = (a + b) / 2
        if mercury_is_retrograde(mid) == retro_a:
            a = mid
        else:
            b = mid
    return (a + b) / 2


def mercury_retrograde_intervals(start: float, end: float) -> list[tuple[float, float]]:
    """Retrograde periods overlapping ``[start, end]``, clipped to it."""
    step = DAY / 4
    intervals = []
    t, retro = start, mercury_is_retrograde(start)
    opened = start if retro else None
    while t < end:
        nt = min(t + step, end)
        now_retro = mercury_is_retrograde(nt)
        if now_retro != retro:
            station = _station_between(t, nt)
            if now_retro:
                opened = station
            else:
                intervals.append((opened, station))
                opened = None
            retro = now_retro
        t = nt
    if opened is not None:
        intervals.append((opened, end))
    return intervals


def next_mercury_station(ts: float) -> tuple[float, str]:
    """When Mercury next stations, and which way it turns ("retrograde" or "direct")."""
    retro = mercury_is_retrograde(ts)
    t = ts
    while mercury_is_retrograde(t + DAY) == retro:
        t += DAY
    return _station_between(t, t + DAY), "direct" if retro else "retrograde"


def moon_age(ts: float) -> float:
    """Days since the last new moon."""
    return (julian_day(ts) - REFERENCE_NEW_MOON) % SYNODIC_MONTH


def moon_phase(ts: float) -> float:
    """0 = new, 0.5 = full."""
    return moon_age(ts) / SYNODIC_MONTH


def moon_illumination(ts: float) -> float:
    return (1 - math.cos(2 * math.pi * moon_phase(ts))) / 2


def moon_phase_name(ts: float) -> str:
    return MOON_PHASES[int(moon_phase(ts) * 8 + 0.5) % 8]


def lunations(start: float, end: float) -> list[tuple[float, str]]:
    """New and full moons in ``[start, end]``."""
    events = []
    half = SYNODIC_MONTH / 2
    k = math.floor((julian_day(start) - REFERENCE_NEW_MOON) / half)
    while True:
        jd = REFERENCE_NEW_MOON + k * half
        ts = (jd - 2440587.5) * DAY
        if ts > end:
            return events
        if ts >= start:
            events.append((ts, "new" if k % 2 == 0 else "full"))
        k += 1


def zodiac_sign(longitude: float) -> tuple[str, str]:
    return ZODIAC[int(longitude % 360 // 30)]
