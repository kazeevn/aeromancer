"""Just enough real astronomy to make the pseudo-science sound authoritative.

Planet positions use the JPL "Approximate Positions of the Planets" Keplerian
elements (E. M. Standish, valid 1800-2050), good to a fraction of a degree,
with their longitudes moved from the J2000 equinox to the equinox of date.
The Moon uses the mean synodic month, good to about half a day. Solar time,
sunrise and the Sun's height follow from the same elements, good to a minute.
"""

from __future__ import annotations

import calendar
import math
import time

J2000 = 2451545.0
SYNODIC_MONTH = 29.530588853  # days
REFERENCE_NEW_MOON = 2451550.26  # JD, 2000-01-06 18:14 UTC
DAY = 86400.0
OBLIQUITY = math.radians(23.43928)  # of the ecliptic, J2000
SUNRISE_ALTITUDE = math.radians(-0.833)  # the upper limb on the horizon, with refraction

# The seven classical planets in the Chaldean order, slowest first, which is
# also the order in which they rule the hours of the day.
CHALDEAN = ("Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury", "Moon")
DAY_RULERS = ("Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Sun")  # Monday first
PLANET_GLYPHS = {"Saturn": "♄", "Jupiter": "♃", "Mars": "♂", "Sun": "☉", "Venus": "♀", "Mercury": "☿", "Moon": "☽"}

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


def _of_date(longitude: float, jd: float) -> float:
    """A longitude on the J2000 ecliptic, as the elements give it, counted from the equinox of date instead, as the
    tropical zodiac counts: the equinox slides back along the ecliptic by the general precession, 5029.0966″ a century."""
    return (longitude + 5029.0966 / 3600 * (jd - J2000) / 36525) % 360


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
    """Geocentric ecliptic longitude of Mercury, degrees from the equinox of date."""
    jd = julian_day(ts)
    mx, my, _ = _heliocentric("mercury", jd)
    ex, ey, _ = _heliocentric("earth", jd)
    return _of_date(math.degrees(math.atan2(my - ey, mx - ex)), jd)


def sun_longitude(ts: float) -> float:
    """Ecliptic longitude of the Sun, degrees from the equinox of date."""
    jd = julian_day(ts)
    ex, ey, _ = _heliocentric("earth", jd)
    return _of_date(math.degrees(math.atan2(-ey, -ex)), jd)


def sun_reaches(longitude: float, ts: float) -> float:
    """When the Sun next reaches ecliptic ``longitude`` (degrees) after ``ts``, to a few seconds."""
    rate = 360 / 365.2422 / DAY  # degrees a second, on average
    t = ts + (longitude - sun_longitude(ts)) % 360 / rate
    for _ in range(3):
        t += ((longitude - sun_longitude(t) + 180) % 360 - 180) / rate
    return t


def sun_declination(ts: float) -> float:
    """Degrees north of the celestial equator."""
    return math.degrees(math.asin(math.sin(OBLIQUITY) * math.sin(math.radians(sun_longitude(ts)))))


def equation_of_time(ts: float) -> float:
    """Minutes that a sundial runs ahead of mean solar time."""
    lam = math.radians(sun_longitude(ts))
    right_ascension = math.degrees(math.atan2(math.cos(OBLIQUITY) * math.sin(lam), math.cos(lam)))
    base, rate = _ELEMENTS["earth"]
    jd = julian_day(ts)
    mean_sun = _of_date(base[3] + rate[3] * (jd - J2000) / 36525 + 180, jd)
    return 4 * ((mean_sun - right_ascension + 180) % 360 - 180)


def zone_longitude(ts: float) -> float:
    """The longitude whose mean solar time the local clock keeps, for when home's is unknown."""
    return time.localtime(ts).tm_gmtoff / 240


def solar_hours(ts: float, longitude: float) -> float:
    """Local apparent solar time, as a sundial at ``longitude`` shows it: 12 is when the Sun is highest."""
    return (ts / 3600 + longitude / 15 + equation_of_time(ts) / 60) % 24


def sun_elevation(ts: float, latitude: float, longitude: float) -> float:
    """Degrees above the horizon, without refraction."""
    hour_angle = math.radians((solar_hours(ts, longitude) - 12) * 15)
    lat, dec = math.radians(latitude), math.radians(sun_declination(ts))
    return math.degrees(math.asin(math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(hour_angle)))


def half_day_hours(ts: float, latitude: float) -> float:
    """Hours from sunrise to solar noon (and from noon to sunset) around ``ts``."""
    lat, dec = math.radians(latitude), math.radians(sun_declination(ts))
    cos_h = (math.sin(SUNRISE_ALTITUDE) - math.sin(lat) * math.sin(dec)) / (math.cos(lat) * math.cos(dec))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_h)))) / 15


def planetary_hours(ts: float, latitude: float, longitude: float) -> list[tuple[float, float, str]]:
    """The 24 unequal hours ``(start, end, ruler)`` of the planetary day around ``ts``.

    A planetary day runs from sunrise to sunrise. Its daylight and its night
    are each cut into 12 equal hours; the weekday's planet rules the first,
    and the rest follow in the Chaldean order.
    """
    half = half_day_hours(ts, latitude)
    since_sunrise = (solar_hours(ts, longitude) - (12 - half)) % 24
    sunrise = ts - since_sunrise * 3600
    sunset = sunrise + 2 * half * 3600
    next_sunrise = sunrise + DAY
    day = (sunset - sunrise) / 12
    night = (next_sunrise - sunset) / 12
    first = CHALDEAN.index(DAY_RULERS[time.localtime(sunrise).tm_wday])
    hours = []
    for i in range(24):
        a = sunrise + i * day if i < 12 else sunset + (i - 12) * night
        hours.append((a, a + (day if i < 12 else night), CHALDEAN[(first + i) % 7]))
    return hours


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


def _last_mercury_station(ts: float) -> float:
    retro = mercury_is_retrograde(ts)
    t = ts
    while mercury_is_retrograde(t - DAY) == retro:
        t -= DAY
    return _station_between(t - DAY, t)


def _mercury_reaches(longitude: float, ts: float, step: float) -> float:
    """When direct Mercury, followed from ``ts`` in steps of ``step`` seconds (back if negative), reaches ``longitude``."""

    def past(t):
        return ((mercury_longitude(t) - longitude + 540) % 360 - 180) * step > 0

    t = ts
    while not past(t + step):
        t += step
    a, b = t, t + step
    for _ in range(30):
        mid = (a + b) / 2
        a, b = (a, mid) if past(mid) else (mid, b)
    return (a + b) / 2


def mercury_cycle(ts: float) -> tuple[float, float, float, float]:
    """``(shadow begins, turns retrograde, turns direct, shadow ends)`` for the retrograde ``ts`` is in or before.

    Before a retrograde, Mercury crosses the degree where it will later turn
    direct; after it, it must regain the degree where it turned back.
    Astrologers call these stretches the shadow.
    """
    if mercury_is_retrograde(ts):
        retro, (direct, _) = _last_mercury_station(ts), next_mercury_station(ts)
    else:
        direct = _last_mercury_station(ts)
        retro = _last_mercury_station(direct - DAY)
        if ts >= _mercury_reaches(mercury_longitude(retro), direct, DAY):  # past the last one's shadow: the next one
            retro, _ = next_mercury_station(ts)
            direct, _ = next_mercury_station(retro + DAY)
    start = _mercury_reaches(mercury_longitude(direct), retro, -DAY)
    return start, retro, direct, _mercury_reaches(mercury_longitude(retro), direct, DAY)


def mercury_shadow(ts: float) -> tuple[str, float, float] | None:
    """``("pre", start, station)`` or ``("post", station, end)`` while direct Mercury crosses ground it retraces."""
    start, retro, direct, end = mercury_cycle(ts)
    if start <= ts < retro:
        return "pre", start, retro
    if direct <= ts < end:
        return "post", direct, end
    return None


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


def chinese_new_year(year: int) -> float:
    """Midnight (China time, UTC+8) starting the day of the new moon that begins the Chinese year.

    That is the first new moon on or after 21 January, which holds for the
    years this oracle will see.
    """
    china = 8 * 3600
    jan21 = calendar.timegm((year, 1, 21, 0, 0, 0)) - china
    new_moon = next(t for t, kind in lunations(jan21, jan21 + 31 * DAY) if kind == "new")
    return (new_moon + china) // DAY * DAY - china


def zodiac_sign(longitude: float) -> tuple[str, str]:
    return ZODIAC[int(longitude % 360 // 30)]
