"""Strictly pseudo-scientific analysis of the timeseries.

Every number below is computed honestly from the data. Every interpretation
is not. Nothing here means anything; please do not open a window because
Mercury told you to (open it because CO2 is above 1000 ppm).
"""

from __future__ import annotations

import bisect
import cmath
import hashlib
import math
import random
import statistics
from datetime import datetime

from . import astro, lore

PHI = (1 + 5**0.5) / 2
SCHUMANN_HZ = 7.83
AIRING_PM25 = 35  # µg/m³ of outdoor PM2.5 (the US EPA 24-hour standard) above which airing trades CO2 for particles


def hazy(outdoor_pm25: float | None) -> bool:
    """Whether the outside air is too dirty to air the room with; unknown counts as clean."""
    return outdoor_pm25 is not None and outdoor_pm25 >= AIRING_PM25


def airing(outdoor_pm25: float | None) -> str:
    """What to do about stale air, given the latest outdoor PM2.5 (None when unknown)."""
    if hazy(outdoor_pm25):
        return (
            f"But the veil beyond the glass is thick with haze ({outdoor_pm25:.0f} µg/m³ of PM2.5): keep the windows "
            "sealed, thin the crowd, and let the purifier sing."
        )
    return "Open a window and let the outside in."

# Upper CO2 bound (ppm), name, Sanskrit name, reading.
CHAKRAS = (
    (450, "Crown", "Sahasrara", "Transcendent. Indistinguishable from outdoor air, or the sensor is outside."),
    (600, "Third Eye", "Ajna", "Clairvoyant ventilation. You can see the future, and it is well aired."),
    (800, "Throat", "Vishuddha", "Clear communication between your lungs and the atmosphere."),
    (1000, "Heart", "Anahata", "Warm, loving, slightly shared air."),
    (1400, "Solar Plexus", "Manipura", "Willpower is high. Oxygen is less so."),
    (2000, "Sacral", "Svadhishthana", "Creative energy is pooling near the ceiling."),
    (math.inf, "Root", "Muladhara", "Deeply grounded. Possibly asleep. {airing}"),
)

LIFE_PATHS = {
    1: "The Pioneer. This room leads; other rooms follow its exhaust.",
    2: "The Diplomat. Balances inhale and exhale with grace.",
    3: "The Communicator. Someone in here talks a lot, and the CO2 knows.",
    4: "The Builder. Stable, square, probably an office.",
    5: "The Adventurer. Restless air that wants to be elsewhere.",
    6: "The Nurturer. Holds its warmth, and its carbon, close.",
    7: "The Seeker. Introspective air contemplating the ventilation duct.",
    8: "The Powerhouse. Abundant in all things, mostly molecules.",
    9: "The Humanitarian. Breathed by many, judged by none.",
    11: "Master Number 11: The Illuminator. A rare and suspicious sign.",
    22: "Master Number 22: The Master Builder. The HVAC engineers are pleased.",
    33: "Master Number 33: The Master Teacher. The air has lessons for you.",
}

AURAS = (  # (upper CO2 bound, name, hue, saturation %, reading)
    (500, "Celestial White", 200, 15, "Pure, unburdened, possibly outdoors."),
    (650, "Azure", 205, 85, "Calm, clear, and well ventilated."),
    (800, "Emerald", 150, 70, "Growth and healing. Plants would approve."),
    (1000, "Golden", 45, 90, "Radiant and productive, for now."),
    (1300, "Amber", 28, 90, "Passionate air with a hint of meeting room."),
    (1800, "Crimson", 355, 75, "Intense. Concentration is high and dropping."),
    (math.inf, "Murky Brown", 25, 35, "The aura of a submarine at the end of a long patrol."),
)

# (what it follows, direction) -> (persona, reading)
SIGNAL_PERSONAS = {
    ("co2", 1): ("Echo of the Breath", "It rises and falls with your CO\u2082. Possibly a raw sensor reading; certainly a kindred spirit."),
    ("co2", -1): ("The Inverse Breath", "It sinks whenever you exhale. It may be counting the oxygen you have left."),
    ("temperature", 1): ("Ember Spirit", "It warms when the room warms. A second thermometer, or a small fire elemental."),
    ("temperature", -1): ("Frost Spirit", "It cools as the room warms, in quiet protest."),
    ("time", 1): ("The Ascender", "It climbs steadily whatever the air does. Something inside is counting, or warming up."),
    ("time", -1): ("The Wanderer", "It drifts steadily downward, as if slowly walking away from us."),
    ("moon", 1): ("Moon Listener", "It brightens with the Moon. Nobody expected this, least of all the manufacturer."),
    ("moon", -1): ("Moon Shunner", "It fades as the Moon fills. It prefers the dark."),
}
SLEEPER = ("The Sleeper", "It has not moved at all. It is waiting for something.")
TRICKSTER = ("The Trickster", "It moves, but follows nothing we can measure. Perhaps something we cannot.")
CORRELATE_NAMES = {"co2": "CO\u2082", "temperature": "temperature", "time": "the passage of time", "moon": "the Moon"}
SIGNAL_FOLLOWS_AT = 0.6  # |r| needed to say a signal follows something

CERTAINTIES = (
    "5σ (vibes)",
    "p < 0.05, by assertion",
    "peer-reviewed by the Moon",
    "confirmed by a pendulum",
    "cosmic",
    "statistically spiritual",
    "beyond reasonable doubt, and reason",
    "double-blind (eyes closed)",
)

# Everything the household measures that the Oracle invites, in seating order:
# quantity -> (label on a figure, name in a sentence, group).
GUESTS = {
    "co2": ("CO₂", "your CO₂", "zytemp"),
    "temperature": ("Meter °C", "the meter's temperature", "zytemp"),
    "humidity": ("Meter RH", "the meter's humidity", "zytemp"),
    "blueair_pm25": ("PM2.5", "the purifier's PM2.5", "blueair"),
    "blueair_voc": ("VOC", "the purifier's VOC", "blueair"),
    "blueair_temperature": ("Purifier °C", "the purifier's temperature", "blueair"),
    "blueair_humidity": ("Purifier RH", "the purifier's humidity", "blueair"),
    "blueair_fan_speed": ("Fan", "the purifier's fan", "blueair"),
    "outdoor_pm25": ("Haze", "the outdoor haze", "outdoor"),
    "outdoor_temperature": ("Outdoor °C", "the outdoor temperature", "outdoor"),
    "outdoor_humidity": ("Outdoor RH", "the outdoor humidity", "outdoor"),
    "outdoor_wind_speed": ("Wind", "the wind", "outdoor"),
    "outdoor_rain": ("Rain", "the rain", "outdoor"),
}
SKY = {"sun": ("Sun", "the Sun", "sky"), "moon": ("Moon", "the Moon", "sky")}

# The sensor society
CELL_SECONDS = 600  # the common grid everyone is resampled onto: cells this long,
SOCIETY_CELLS = (144, 1000)  # but at least and at most this many
MIN_CELLS = 24  # cells two guests must share before they can know each other
FRIENDS_AT = 0.5  # |r| that makes a friend, or an enemy
STRANGERS_BELOW = 0.3  # a guest whose best |r| is below this talks to no one

# The household choir
CHOIR_POINTS = 256  # a power of two, for the FFT
MIDDLE_C = 261.63  # Hz; the middle rhythm is transposed to sound near it, to find the tonic
EARTH_OCTAVES = 6  # the Schumann resonance, raised into the audible range
NOW_SECONDS = 3600  # the air is judged by its last hour
# How each guest's air feels: (comfortable from, to, how far beyond makes it unbearable, weight).
COMFORT = {
    "co2": (0, 700, 1000, 1.0),  # ppm; 1000 is where a window is due
    "temperature": (20, 27, 4, 0.6),  # °C
    "humidity": (40, 60, 20, 0.4),  # %
    "blueair_pm25": (0, 12, 43, 1.0),  # µg/m³, from the WHO's yearly guideline to NEA's band I
    "blueair_voc": (0, 300, 1900, 0.5),  # ppb
    "blueair_temperature": (20, 27, 4, 0.6),
    "blueair_humidity": (40, 60, 20, 0.4),
    "outdoor_pm25": (0, 12, 88, 1.0),  # µg/m³; 100 is unhealthy for everyone
    "outdoor_temperature": (20, 31, 5, 0.5),
    "outdoor_humidity": (0, 85, 15, 0.3),
    "outdoor_wind_speed": (0, 8, 9, 0.4),  # m/s; 17 is a gale
    "outdoor_rain": (0, 0, 16, 0.3),  # mm/h; 16 is a downpour
}
UNITS = {"co2": "ppm", "pm25": "µg/m³", "voc": "ppb", "temperature": "°C", "humidity": "%", "fan_speed": "", "wind_speed": "m/s", "rain": "mm/h"}
BANDS = ((1 / 3, "clear"), (2 / 3, "middling"), (math.inf, "heavy"))
# The mood, by how heavy the air is inside (rows) and outside (columns): (name, reading).
MOODS = (
    (
        ("Serenade", "Clear air within and without: the house sings with its windows open."),
        ("Pastorale", "A clear house under a middling sky: a country song with clouds in it."),
        ("Sanctuary", "The world outside is grim and the house holds it off: a hymn sung behind closed shutters."),
    ),
    (
        ("Invitation", "The world sings brighter than the house, and calls to it."),
        ("Nocturne", "Middling air on both sides of the glass: a night piece, neither sad nor glad."),
        ("Vigil", "The house strains to keep out a heavy world: a song for the watch."),
    ),
    (
        ("Longing", "Heavy air within, clear air without: the house sings of the open window it lacks."),
        ("Lament", "The house is heavy and the world no comfort: a lament over a ground."),
        ("Dirge", "Heavy air within and without, which Plato would have sung in Mixolydian, had he been asked."),
    ),
)
MOODS_ALONE = (  # with no word from outside
    ("Serenade", "Clear air within: the house sings to itself."),
    ("Nocturne", "Middling air within: a night piece, neither sad nor glad."),
    ("Dirge", "Heavy air within: a song for the end of a long patrol."),
)
PHRASE_BEATS = 8
# Each guest's leitmotif: (theme, scale degree it sings around, octave, beats a note, change in the signal a step up).
THEMES = {
    "co2": ("breath", 0, 4, 2, 40),
    "temperature": ("warmth", 4, 4, 1, 0.3),
    "humidity": ("damp", 2, 3, 4, 2),
    "blueair_pm25": ("dust", 0, 5, 0.5, 3),
    "blueair_voc": ("vapour", 2, 4, 2, 150),
    "blueair_temperature": ("warmth", 2, 5, 1, 0.3),
    "blueair_humidity": ("damp", 4, 3, 4, 2),
    "blueair_fan_speed": ("ground", 0, 2, 2, None),
    "outdoor_pm25": ("haze", 0, 3, 4, 10),
    "outdoor_temperature": ("warmth", 4, 4, 1, 0.3),
    "outdoor_humidity": ("damp", 2, 3, 4, 2),
    "outdoor_wind_speed": ("harp", 0, 2, 1, None),
    "outdoor_rain": ("rain", 0, 6, 1, None),
}
CADENCE_BEATS = 4

# Souls present
OUTDOOR_CO2 = 425.0  # ppm, the planet's background in 2026
EXHALED = 18.0  # litres of CO2 a resting adult breathes out per hour
ROOM_VOLUMES = {"bedroom": 30, "living room": 60, "kitchen": 20, "study": 30, "office": 40}  # m³
DEFAULT_VOLUME = 40.0
ASSUMED_AIR_CHANGES = 0.5  # per hour, when the CO2 will not tell
SOUL_READINGS = (  # (upper bound, reading)
    (0.0, "Negative souls: something here breathes in more than anyone breathes out. Check behind the purifier."),
    (0.3, "Nobody is here, or somebody very calm. Possibly a ghost."),
    (0.8, "Part of a soul: someone present in spirit, asleep, or a cat."),
    (1.5, "One soul, breathing alone. Solitude suits the air."),
    (2.5, "Two souls share the air. The CO₂ suggests they talk."),
    (math.inf, "A gathering! The pseudoscientist approves of company; the CO₂ does not."),
)

# Birth certificates
BIORHYTHMS = (("physical", 23), ("emotional", 28), ("intellectual", 33))  # days
MEMBERS = {"zytemp": "the meter", "blueair": "the purifier", "island": "the island's PM2.5", "weather": "the weather"}

# The celestial clock
MIN_DAILY_SPAN = 18 * 3600  # seconds of data a guest needs before it has a daily rhythm
ASPECTS = (  # (name, angle, orb, verb)
    ("conjunction", 0, 10, "is conjunct"),
    ("sextile", 60, 6, "sextiles"),
    ("square", 90, 8, "squares"),
    ("trine", 120, 8, "trines"),
    ("opposition", 180, 10, "opposes"),
)

# The ward: NEA's bands for 1-hour PM2.5, µg/m³
PM25_BANDS = ((55, "I", "normal"), (150, "II", "elevated"), (250, "III", "high"), (math.inf, "IV", "very high"))
WARDS = (  # (lower bound of the share held back, reading)
    (0.8, "An impregnable ward."),
    (0.5, "A sturdy ward."),
    (0.2, "A leaky ward."),
    (0.0, "A ward in name only."),
    (-math.inf, "The ward is inverted: the house makes its own haze."),
)

# The five elements
OVERCOME_VERBS = {"Wood": "parts", "Earth": "dams", "Water": "quenches", "Fire": "melts", "Metal": "chops"}

# The winds
CALM = 0.5  # m/s; slower air is no wind at all

# The I Ching: who casts each line, from the bottom, as (quantity, name in a sentence, unit, decimals).
# The lower trigram is the home, the upper the world.
CASTERS = (
    ("co2", "your breath", "ppm", 0),
    ("temperature", "the warmth", "°C", 1),
    ("blueair_pm25", "the dust", "µg/m³", 0),
    ("outdoor_pm25", "the haze", "µg/m³", 0),
    ("outdoor_wind_speed", "the wind", "m/s", 1),
    ("moon", "the Moon", "", 0),
)
INNER = {  # the lower trigram, cast by breath, warmth and dust
    "Qian": "Inside, breath, warmth and dust all rise: the Creative at full strength, and getting stuffy.",
    "Dui": "Inside, breath and warmth rise as the dust settles: the Joyous. Someone is home, and comfortable.",
    "Li": "Inside, breath and dust rise as the warmth fades: the Clinging. Where there is fire there is clarity; check the kitchen.",
    "Zhen": "Inside, only your breath rises: Thunder, the Arousing. Someone has just woken up, or walked in.",
    "Xun": "Inside, warmth and dust rise as your breath recedes: the Gentle. The house exhales on its own.",
    "Kan": "Inside, only the warmth rises: the Abysmal. Comfort hides a danger, probably the thermostat.",
    "Gen": "Inside, only the dust rises: Keeping Still. The particles meditate on your furniture.",
    "Kun": "Inside, breath, warmth and dust all fall: the Receptive. The house yields; let it rest.",
}
OUTER = {  # the upper trigram, cast by the haze, the wind and the Moon
    "Qian": "Outside, the haze thickens, the wind rises and the Moon waxes: Heaven leans on the windows. Keep them shut.",
    "Dui": "Outside, haze and wind rise under a waning Moon: the Joyous lake reflects a smoky sky.",
    "Li": "Outside, the haze thickens under a waxing Moon as the wind drops: the Clinging. The haze stays for dinner.",
    "Zhen": "Outside, only the haze rises: Thunder rolls in, measured in micrograms.",
    "Xun": "Outside, the wind rises under a waxing Moon and the haze thins: the Gentle wind carries it off.",
    "Kan": "Outside, only the wind rises: the Abysmal. Water is on its way.",
    "Gen": "Outside, haze and wind fall under a waxing Moon: Keeping Still. The mountain waits for the haze to pass.",
    "Kun": "Outside, the haze thins, the wind drops and the Moon wanes: the Receptive. The world asks nothing of you.",
}
JUDGEMENTS = {  # what some hexagrams mean for air in particular
    1: "Everything rises. Open nothing: the haze rises too.",
    2: "Everything yields. A fine hour for a nap.",
    11: "Peace: inside thrives while outside wanes. Stay in.",
    12: "Standstill: the air goes nowhere, and neither should you.",
    13: "Fellowship with Men, the most gregarious of hexagrams: invite someone over, then count the souls.",
    29: "The Abysmal, doubled: danger within and without. Mind the humidity.",
    45: "Gathering Together: the souls assemble.",
    50: "The Caldron: something is cooking. Ask the VOC.",
    57: "The Gentle, doubled: wind within and without. The fan approves.",
    59: "Dispersion: exactly what the purifier is for.",
    63: "After Completion: everything is in its place, for now.",
    64: "Before Completion: the air is nearly right. Nearly.",
}


def _seed(*parts) -> int:
    return int.from_bytes(hashlib.sha256(repr(parts).encode()).digest()[:8], "big")


def _pick(options, *seed_parts):
    return options[_seed(*seed_parts) % len(options)]


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    try:
        return statistics.correlation(xs, ys)
    except statistics.StatisticsError:  # one of the series is constant
        return None


def _resample(points: list[tuple[float, float]], n: int) -> list[float]:
    """Linearly interpolate onto ``n`` evenly spaced times."""
    t0, t1 = points[0][0], points[-1][0]
    out, j = [], 0
    for i in range(n):
        t = t0 + (t1 - t0) * i / (n - 1)
        while j < len(points) - 2 and points[j + 1][0] < t:
            j += 1
        (ta, va), (tb, vb) = points[j], points[j + 1]
        out.append(va if tb == ta else va + (vb - va) * (t - ta) / (tb - ta))
    return out


def _detrend(values: list[float]) -> list[float]:
    xs = range(len(values))
    slope, intercept = statistics.linear_regression(xs, values)
    return [v - (slope * x + intercept) for x, v in zip(xs, values)]


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _interpolate(points: list[tuple[float, float]], times: list[float], t: float) -> float:
    """Value of ``points`` at ``t``; ``times`` is their precomputed timestamps."""
    j = min(max(bisect.bisect_left(times, t), 1), len(points) - 1)
    (ta, va), (tb, vb) = points[j - 1], points[j]
    return va if tb == ta else va + (vb - va) * (t - ta) / (tb - ta)


def _downsample(values: list[float], n: int) -> list[float]:
    if len(values) <= n:
        return values
    return [statistics.fmean(values[i * len(values) // n : (i + 1) * len(values) // n]) for i in range(n)]


def _digital_root(n: int) -> int:
    while n > 9 and n not in (11, 22, 33):
        n = sum(int(d) for d in str(n))
    return n


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def _and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _duration(seconds: float) -> str:
    minutes = round(abs(seconds) / 60)
    if minutes < 60:
        return f"{minutes} min"
    if minutes >= 48 * 60:
        return f"{round(minutes / 1440)} days"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h" + (f" {minutes} min" if minutes else "")


def _clock(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def _date(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%b %-d")


def _planet(name: str) -> str:
    return f"the {name}" if name in ("Sun", "Moon") else name


def _named(name: str) -> tuple[str, str, str]:
    """A guest's or a celestial body's ``(label, name in a sentence, group)``."""
    return GUESTS.get(name) or SKY[name]


def _median_step(points: list[tuple[float, float]]) -> float:
    return statistics.median(b[0] - a[0] for a, b in zip(points, points[1:])) if len(points) > 1 else 0.0


def _bucket_means(points: list[tuple[float, float]], seconds: float) -> list[tuple[float, float]]:
    """``(mean ts, mean value)`` per ``seconds``-long interval that has points, in time order."""
    buckets: dict[int, list[tuple[float, float]]] = {}
    for t, v in points:
        buckets.setdefault(int(t // seconds), []).append((t, v))
    return [(statistics.fmean(t for t, _ in b), statistics.fmean(v for _, v in b)) for _, b in sorted(buckets.items())]


def _grid(start: float, end: float, n: int) -> list[float]:
    """The middles of ``n`` equal cells spanning ``start`` to ``end``."""
    step = (end - start) / n
    return [start + step * (i + 0.5) for i in range(n)]


def _on_grid(points: list[tuple[float, float]], grid: list[float], max_gap: float) -> list[float | None]:
    """``points`` in each cell of ``grid``: their mean there, else interpolated across a gap of up to ``max_gap``."""
    half = (grid[1] - grid[0]) / 2
    times = [t for t, _ in points]
    out = []
    for g in grid:
        a, b = bisect.bisect_left(times, g - half), bisect.bisect_left(times, g + half)
        if b > a:
            out.append(statistics.fmean(v for _, v in points[a:b]))
        elif 0 < a < len(points) and times[a] - times[a - 1] <= max_gap:
            (ta, va), (tb, vb) = points[a - 1], points[a]
            out.append(va + (vb - va) * (g - ta) / (tb - ta))
        else:
            out.append(None)
    return out


def _paired_pearson(a: list[float | None], b: list[float | None], lag: int = 0, min_n: int = MIN_CELLS) -> float | None:
    """Correlation of ``a`` with ``b`` ``lag`` cells later, over the cells both have."""
    xs, ys = (a, b[lag:]) if lag >= 0 else (a[-lag:], b)
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < min_n:
        return None
    return _pearson([x for x, _ in pairs], [y for _, y in pairs])


def _best_lag(a, b, max_lag: int, sign: int = 1, min_n: int = MIN_CELLS) -> tuple[int, float] | None:
    """``(lag, r)``: how many cells later ``b`` best follows ``a`` (or, with ``sign`` -1, best opposes it)."""
    scored = [(lag, r) for lag in range(-max_lag, max_lag + 1) if (r := _paired_pearson(a, b, lag, min_n)) is not None]
    return max(scored, key=lambda s: (sign * s[1], -abs(s[0])), default=None)


def _fft(values: list[complex]) -> list[complex]:
    """The discrete Fourier transform; ``len(values)`` must be a power of two."""
    n = len(values)
    if n == 1:
        return list(values)
    even, odd = _fft(values[0::2]), _fft(values[1::2])
    turned = [cmath.exp(-2j * math.pi * k / n) * o for k, o in enumerate(odd)]
    return [e + t for e, t in zip(even, turned)] + [e - t for e, t in zip(even, turned)]


def _solve(rows: list[tuple[float, ...]], ys: list[float]) -> list[float] | None:
    """Least-squares coefficients ``x`` of ``ys ≈ rows · x``, by the normal equations; None if they are singular."""
    n = len(rows[0])
    m = [[sum(r[i] * r[j] for r in rows) for j in range(n)] + [sum(r[i] * y for r, y in zip(rows, ys))] for i in range(n)]
    for c in range(n):
        pivot = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[pivot][c]) < 1e-9:
            return None
        m[c], m[pivot] = m[pivot], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]


def _where(placements, device: str, ts: float):
    """Where ``device`` was at ``ts``: the latest of its ``placements`` (in time order) up to then, or None."""
    found = None
    for p in placements:
        if p.device == device and p.ts <= ts:
            found = p
    return found


def _chakra_for(ppm: float):
    return next(c for c in CHAKRAS if ppm < c[0])


def chakra_of(ppm: float) -> str:
    return _chakra_for(ppm)[1]


def chakra_residency(co2, outdoor_pm25: float | None = None):
    counts = [0] * len(CHAKRAS)
    for _, v in co2:
        counts[CHAKRAS.index(_chakra_for(v))] += 1
    total = sum(counts)
    bands = [
        {"name": name, "sanskrit": sanskrit, "upper": None if math.isinf(upper) else upper, "share": c / total}
        for (upper, name, sanskrit, _), c in zip(CHAKRAS, counts)
    ]
    dominant = max(range(len(CHAKRAS)), key=counts.__getitem__)
    return {
        "id": "chakra",
        "title": "Chakra residency",
        "headline": f"{CHAKRAS[dominant][1]} chakra",
        "body": f"Your air dwelt {counts[dominant] / total:.0%} of the time in {CHAKRAS[dominant][1]} "
        f"({CHAKRAS[dominant][2]}). {CHAKRAS[dominant][3].format(airing=airing(outdoor_pm25))}",
        "bands": bands,
    }


def aura(co2, temperature):
    mean = statistics.fmean(v for _, v in co2)
    _, name, hue, saturation, reading = next(a for a in AURAS if mean < a[0])
    temp_note = ""
    if temperature:
        t = statistics.fmean(v for _, v in temperature)
        if t >= 24:
            temp_note = " A warm halo suggests unresolved radiator energy."
        elif t <= 19:
            temp_note = " A cool rim suggests emotional draughts."
    return {
        "id": "aura",
        "title": "Aura",
        "headline": name,
        "body": reading + temp_note,
        "hue": hue,
        "saturation": saturation,
    }


def lunar(co2, end):
    illum = [astro.moon_illumination(t) for t, _ in co2]
    r = _pearson(illum, [v for _, v in co2])
    if r is None:
        coupling = "The Moon declined to comment: the window is too short for lunar resolution."
    elif abs(r) < 0.2:
        coupling = f"Lunar coupling r = {r:+.2f}. Your room is emotionally independent of the Moon."
    elif r > 0:
        coupling = f"Lunar coupling r = {r:+.2f}. Your CO2 waxes with the Moon. Werewolf-adjacent."
    else:
        coupling = f"Lunar coupling r = {r:+.2f}. Your room exhales as the Moon fills. Tidal ventilation."
    return {
        "id": "moon",
        "title": "Lunar influence",
        "headline": astro.moon_phase_name(end),
        "body": f"{astro.moon_illumination(end):.0%} illuminated, {astro.moon_age(end):.1f} days old. {coupling}",
        "phase": astro.moon_phase(end),
        "coupling": r,
    }


def mercury(co2, start, end):
    retro_now = astro.mercury_is_retrograde(end)
    station, turn = astro.next_mercury_station(end)
    shadow = astro.mercury_shadow(end)
    intervals = astro.mercury_retrograde_intervals(start, end)
    stuffy = [t for t, v in co2 if v >= 1000]
    blamed = sum(any(a <= t <= b for a, b in intervals) for t in stuffy)
    if not stuffy:
        blame = "No stuffy air (≥1000 ppm) to blame on anyone. Mercury is bored."
    elif blamed:
        blame = f"{blamed / len(stuffy):.0%} of your stuffy air (≥1000 ppm) is attributable to Mercury."
    elif shadow and shadow[1] <= start:
        blame = "Mercury was direct the whole time, but in its shadow: it takes half the blame for your stuffy air."
    else:
        blame = "Mercury was direct the whole time, so the stuffy air is entirely your own doing."
    body = f"{blame} Mercury stations {turn} on {_date(station)}."
    if shadow and shadow[0] == "pre":
        sign = astro.zodiac_sign(astro.mercury_longitude(end))[0]
        body += f" It has walked in its pre-retrograde shadow since {_date(shadow[1])}, over ground in {sign} it will retrace."
    elif shadow:
        body += f" It walks in its post-retrograde shadow until {_date(shadow[2])}, regaining the ground it lost."
    return {
        "id": "mercury",
        "title": "Mercury",
        "headline": "Retrograde ℞" if retro_now else "Direct, in shadow" if shadow else "Direct",
        "body": body,
        "retrograde": retro_now,
        "shadow": {"kind": shadow[0], "start": shadow[1], "end": shadow[2]} if shadow else None,
        "cycle": dict(zip(("shadow_start", "retrograde", "direct", "shadow_end"), astro.mercury_cycle(end))),
        "next_station": station,
        "next_turn": turn,
        "motion_deg_per_day": astro.mercury_motion(end),
    }


def schumann(co2):
    if len(co2) < 16 or co2[-1][0] - co2[0][0] < 600:
        return {
            "id": "schumann",
            "title": "Schumann alignment",
            "headline": "Listening…",
            "body": "At least ten minutes of air are needed to hear the Earth's heartbeat in it.",
            "cents": None,
        }
    n = min(512, len(co2))
    values = _detrend(_resample(co2, n))
    duration = co2[-1][0] - co2[0][0]
    power = [abs(sum(v * cmath.exp(-2j * math.pi * k * i / n) for i, v in enumerate(values))) for k in range(1, n // 2)]
    k = 1 + max(range(len(power)), key=power.__getitem__)
    freq = k / duration
    octaves = math.log2(SCHUMANN_HZ / freq)
    sub_octave = round(octaves)
    cents = (sub_octave - octaves) * 1200
    period = duration / k
    period_text = f"{period / 3600:.1f} h" if period >= 3600 else f"{period / 60:.0f} min"
    sharp = "sharp" if cents > 0 else "flat"
    return {
        "id": "schumann",
        "title": "Schumann alignment",
        "headline": f"Sub-octave {sub_octave}",
        "body": f"Your room breathes once every {period_text}, which is the {_ordinal(sub_octave)} sub-octave of the "
        f"Earth's 7.83 Hz heartbeat, {abs(cents):.0f} cents {sharp}. "
        + ("Spiritually in tune." if abs(cents) < 15 else "A gentle retuning with an open window is advised."),
        "cents": cents,
        "period_s": period,
    }


def golden_ratio(co2):
    if len(co2) < 8:
        return {
            "id": "golden",
            "title": "Divine proportion",
            "headline": "Insufficient breath",
            "body": "Not enough inhales and exhales yet to measure their sacred geometry.",
            "attainment": None,
        }
    w = max(1, len(co2) // 50)
    smooth = [statistics.fmean(v for _, v in co2[max(0, i - w) : i + w + 1]) for i in range(len(co2))]
    rising = falling = 0.0
    for i in range(1, len(co2)):
        dt = co2[i][0] - co2[i - 1][0]
        if smooth[i] > smooth[i - 1]:
            rising += dt
        elif smooth[i] < smooth[i - 1]:
            falling += dt
    if not rising or not falling:
        ratio, attainment = None, 0.0
        body = "Your air only ever goes one way. Sacred geometry requires a return journey."
    else:
        ratio = rising / falling
        attainment = math.exp(-abs(math.log(ratio / PHI)))
        body = (
            f"Your air spends {ratio:.3f}× as long rising as falling; the divine ratio φ is 1.618. "
            + ("Your room is a Fibonacci spiral." if attainment > 0.9 else "The Parthenon would be disappointed.")
        )
    return {
        "id": "golden",
        "title": "Divine proportion",
        "headline": f"{attainment:.0%} golden",
        "body": body,
        "ratio": ratio,
        "attainment": attainment,
    }


def numerology(co2):
    mean = round(statistics.fmean(v for _, v in co2))
    number = _digital_root(mean)
    return {
        "id": "numerology",
        "title": "Life path number",
        "headline": str(number),
        "body": f"Mean {mean} ppm reduces to {number}. {LIFE_PATHS[number]}",
        "number": number,
    }


def zodiac(co2, temperature, end):
    sun, sun_glyph = astro.zodiac_sign(astro.sun_longitude(end))
    mean_co2 = statistics.fmean(v for _, v in co2)
    rising, rising_glyph = astro.zodiac_sign(mean_co2)  # ppm taken as degrees of ecliptic longitude
    lines = [
        {"glyph": sun_glyph, "role": "Sun", "sign": sun, "why": "where the Sun actually is"},
        {"glyph": rising_glyph, "role": "CO₂ rising", "sign": rising, "why": f"{mean_co2:.0f} ppm read as degrees"},
    ]
    if temperature:
        t = statistics.fmean(v for _, v in temperature)
        moon, moon_glyph = astro.zodiac_sign((t + 273.15) * 12)
        lines.append({"glyph": moon_glyph, "role": "Thermal moon", "sign": moon, "why": f"{t:.1f} °C, in kelvin, ×12"})
    return {
        "id": "zodiac",
        "title": "Natal chart of your air",
        "headline": f"{sun}, {rising} rising",
        "body": " · ".join(f"{l['role']} in {l['sign']}" for l in lines),
        "signs": lines,
    }


def horoscope(co2, end, findings, outdoor_pm25: float | None = None):
    """``outdoor_pm25`` is the outdoor PM2.5 now, if known, so that the stars never send you out into it."""
    day = datetime.fromtimestamp(end).strftime("%Y-%m-%d")
    last_hour = [v for t, v in co2 if t >= end - 3600]
    trend = last_hour[-1] - last_hour[0] if len(last_hour) >= 2 else 0
    by_id = {f["id"]: f for f in findings}
    moon_name = by_id["moon"]["headline"]
    opening = _pick(
        (
            "The stars have reviewed your ventilation.",
            "The cosmos has been reading your sensor.",
            "A comet passed near your windowsill today.",
            "The planets have aligned, roughly, with your desk.",
        ),
        day,
    )
    if trend > 50:
        middle = "Something is accumulating, in the room and in your destiny. It is carbon dioxide."
    elif trend < -50:
        middle = "A great release is under way. Someone opened a door, literally and figuratively."
    else:
        middle = "Stability surrounds you, like a cloud of slightly used air."
    omens = []
    if iching_finding := by_id.get("iching"):
        omens.append(f"The I Ching answers with {iching_finding['name']}.")
    if (souls_finding := by_id.get("souls")) and souls_finding["souls"] is not None:
        n = souls_finding["souls"]
        if n >= 1.5:
            omens.append(f"You are not alone: the CO₂ counts {n:.1f} souls.")
        elif n >= 0.8:
            omens.append("The CO₂ counts one soul: yours, presumably.")
        else:
            omens.append(f"The CO₂ counts {n:.1f} souls: be gentle with yourself.")
    if (elements_finding := by_id.get("elements")) and elements_finding.get("colour"):
        omens.append(f"{elements_finding['excess']} weighs on the island: wear {elements_finding['colour']}.")
    if by_id["mercury"]["retrograde"]:
        advice = "With Mercury retrograde, avoid signing contracts in poorly ventilated rooms."
    elif by_id["mercury"]["shadow"]:
        advice = "With Mercury in its shadow, back up your sensors."
    else:
        moon = moon_name if moon_name.endswith("Moon") else moon_name + " Moon"
        if hazy(outdoor_pm25):  # the stars keep the windows shut
            options = ("keep the windows shut and the purifier high.", "water a plant.", "breathe more quietly.", "admire the haze from behind glass.")
        else:
            options = ("air out the bedroom.", "water a plant.", "breathe more quietly.", "stand near a window.")
        advice = f"Under a {moon}, it is an auspicious time to " + _pick(options, day, "advice")
    lucky = round(statistics.fmean(last_hour or [v for _, v in co2]))
    return {
        "id": "horoscope",
        "title": "Today's horoscope",
        "headline": datetime.fromtimestamp(end).strftime("%A, %B %-d"),
        "body": " ".join([opening, middle, *omens, advice, f"Lucky ppm: {lucky}."]),
    }


def _signal_correlations(points, references, start, end) -> dict[str, float | None]:
    values = [v for _, v in points]
    out = {}
    for name, ref in references.items():
        if len(ref) < 2:
            out[name] = None
            continue
        times = [t for t, _ in ref]
        paired = [(v, _interpolate(ref, times, t)) for t, v in points if times[0] <= t <= times[-1]]
        out[name] = _pearson([a for a, _ in paired], [b for _, b in paired])
    out["time"] = _pearson([t for t, _ in points], values)
    # Over shorter windows the Moon's phase just tracks time, so it would steal time's credit.
    if end - start >= 7 * astro.DAY:
        out["moon"] = _pearson([astro.moon_illumination(t) for t, _ in points], values)
    return out


def voices(signals, co2, temperature, start, end):
    """The meter's undocumented codes, each identified by what it moves with, then spiritually."""
    if not signals:
        return {
            "id": "signals",
            "title": "Voices in the wire",
            "headline": "Silence",
            "body": "No unexplained signals in this window. The recorder keeps them now; give it a few minutes to listen.",
            "signals": [],
        }
    entries = []
    for name in sorted(signals):
        points = signals[name]
        values = [v for _, v in points]
        lo, hi = min(values), max(values)
        favourite = statistics.mode(round(v) for v in values)
        correlations = _signal_correlations(points, {"co2": co2, "temperature": temperature}, start, end)
        known = {k: r for k, r in correlations.items() if r is not None}
        best = max(known, key=lambda k: abs(known[k]), default=None)
        if hi == lo:
            persona, reading = SLEEPER
        elif best is not None and abs(known[best]) >= SIGNAL_FOLLOWS_AT:
            persona, reading = SIGNAL_PERSONAS[(best, 1 if known[best] > 0 else -1)]
            reading += f" (r = {known[best]:+.2f} with {CORRELATE_NAMES[best]}.)"
        else:
            persona, reading = TRICKSTER
        entries.append(
            {
                "op": "0x" + name.removeprefix("op_"),
                "persona": persona,
                "reading": f"{reading} Favourite number: {favourite} (0x{favourite:04X}), "
                f"which reduces to {_digital_root(favourite)}.",
                "min": lo,
                "max": hi,
                "favourite": favourite,
                "correlations": correlations,
                "follows": best if persona not in (SLEEPER[0], TRICKSTER[0]) else None,
                "spark": _downsample(values, 48),
            }
        )
    followers = sum(e["follows"] is not None for e in entries)
    return {
        "id": "signals",
        "title": "Voices in the wire",
        "headline": f"{len(entries)} unexplained signal{'s' if len(entries) != 1 else ''}",
        "body": f"The meter whispers {len(entries)} numbers its makers never explained. "
        f"{followers} of them follow something we can measure; the rest answer to forces unknown.",
        "signals": entries,
    }


def _line(points, hour: float) -> tuple[int, float] | None:
    """The line ``points`` cast at ``hour``, and how much they changed over the hour before it.

    7 (young yang) if they rose, 8 (young yin) if not; 9 or 6 (old, so
    changing) if by more than twice their usual hourly change. None if they
    have been silent for three hours.
    """
    hourly = _bucket_means([(t, v) for t, v in points if t < hour], 3600)
    if len(hourly) < 2 or hourly[-1][0] < hour - 3 * 3600:
        return None
    changes = [b - a for (_, a), (_, b) in zip(hourly, hourly[1:])]
    change = changes[-1]
    usual = statistics.median(abs(c) for c in changes) if len(changes) >= 3 else 0
    old = usual > 0 and abs(change) > 2 * usual
    return ((9 if old else 7) if change > 0 else (6 if old else 8)), change


def _coins(*seed_parts) -> int:
    """Three coins, heads 3 and tails 2, as the I Ching is cast when no yarrow stalks are at hand."""
    return sum(3 if _seed(*seed_parts, coin) & 1 else 2 for coin in range(3))


def iching(series: dict[str, list], end: float) -> dict | None:
    """The hexagram of the hour, each line cast by one source; a silent source's line is cast by coins."""
    hour = end // 3600 * 3600
    lines = []
    for i, (name, who, unit, decimals) in enumerate(CASTERS):
        coins = False
        if name == "moon":
            age = astro.moon_age(hour)
            waxing = age < astro.SYNODIC_MONTH / 2
            old = (astro.SYNODIC_MONTH / 2 if waxing else astro.SYNODIC_MONTH) - age < 1  # about to turn
            value = (9 if old else 7) if waxing else (6 if old else 8)
            why = f"{'waxing' if waxing else 'waning'}, {astro.moon_illumination(hour):.0%} lit"
        else:
            points = series.get(name) or (series.get("blueair_temperature") if name == "temperature" else None)
            cast = _line(points, hour) if points else None
            if cast:
                value, change = cast
                moved = "rose" if change > 0 else "fell"
                why = f"{moved} {abs(change):.{decimals}f} {unit}" if round(abs(change), decimals) else f"barely {moved}"
            else:
                value, why, coins = _coins(hour, i), "silent, so cast by coins", True
        lines.append({"caster": who, "value": value, "yang": value in (7, 9), "changing": value in (6, 9), "why": why, "coins": coins})
    if all(line["coins"] for line in lines if line["caster"] != "the Moon"):
        return None  # without a single reading, this would be fortune-telling
    yang = [line["yang"] for line in lines]
    number = lore.hexagram(yang)
    changed = [y != line["changing"] for y, line in zip(yang, lines)]
    becomes = lore.hexagram(changed) if changed != yang else None
    lower, upper = lore.TRIGRAMS[tuple(yang[:3])], lore.TRIGRAMS[tuple(yang[3:])]
    name = lore.HEXAGRAMS[number - 1]
    body = f"{upper[1]} over {lower[1]}. {INNER[lower[0]]} {OUTER[upper[0]]}"
    if number in JUDGEMENTS:
        body += " " + JUDGEMENTS[number]
    if becomes:
        body += f" Its changing lines turn it into {becomes}, {lore.HEXAGRAMS[becomes - 1]}."
    return {
        "id": "iching",
        "title": "The I Ching",
        "headline": f"{number}. {name}",
        "body": body,
        "number": number,
        "name": name,
        "lines": lines,
        "trigrams": [{"name": t[0], "image": t[1], "glyph": t[2], "lines": yang[i : i + 3]} for i, t in ((0, lower), (3, upper))],
        "becomes": {"number": becomes, "name": lore.HEXAGRAMS[becomes - 1], "lines": changed} if becomes else None,
        "cast_at": hour,
    }


def society(guests: dict[str, list], start: float, end: float, placements=(), home=None) -> dict | None:
    """Everyone's correlation with everyone on one grid: who follows whom, and who talks to no one."""
    grid = _grid(start, end, min(SOCIETY_CELLS[1], max(SOCIETY_CELLS[0], round((end - start) / CELL_SECONDS))))
    step = grid[1] - grid[0]
    seats = {}
    for name, points in guests.items():
        cells = _on_grid(points, grid, max(3 * _median_step(points), 2 * step))
        known = [c for c in cells if c is not None]
        if len(known) >= MIN_CELLS and min(known) < max(known):
            seats[name] = cells
    if not seats:
        return None
    # Over less than their own cycle, the Sun and the Moon would only stand in for the passage of time.
    lat, lon = home or (0.0, astro.zone_longitude(end))
    if end - start >= astro.DAY:
        seats["sun"] = [astro.sun_elevation(t, lat, lon) for t in grid]
    if end - start >= 7 * astro.DAY:
        seats["moon"] = [astro.moon_illumination(t) for t in grid]
    names = list(seats)
    ties = {}
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if (r := _paired_pearson(seats[a], seats[b])) is not None:
                ties[a, b] = r
    friends = {n: sum(abs(r) >= FRIENDS_AT for pair, r in ties.items() if n in pair) for n in names}
    reach = {n: max((abs(r) for pair, r in ties.items() if n in pair), default=0.0) for n in names}
    celestial = [SKY[n][1] for n in SKY if n in seats]
    company = f", {_and(celestial)} among them" if celestial else "; the Sun and the Moon sent their regrets"
    lines = [f"{len(names)} guest{'s' if len(names) > 1 else ''} came{company}."]

    cross = {pair: r for pair, r in ties.items() if _named(pair[0])[2] != _named(pair[1])[2]}
    soulmates = max(cross, key=cross.get, default=None)
    if soulmates and cross[soulmates] >= FRIENDS_AT:
        a, b = soulmates
        lag = (_best_lag(seats[a], seats[b], min(len(grid) // 6, max(1, round(3 * 3600 / step)))) or (0, 0))[0]
        text = f"{_capital(_named(a)[1])} and {_named(b)[1]} are inseparable (r = {ties[soulmates]:+.2f})"
        if lag:
            leader, follower = (a, b) if lag > 0 else (b, a)
            text += f"; {_named(follower)[1]} follows {_named(leader)[1]} by {_duration(abs(lag) * step)}"
        lines.append(text + ".")
    else:
        soulmates = None
    nemeses = min(ties, key=ties.get, default=None)
    if nemeses and ties[nemeses] <= -FRIENDS_AT:
        a, b = nemeses
        lines.append(f"{_capital(_named(a)[1])} cannot stand {_named(b)[1]} (r = {ties[nemeses]:+.2f}).")
    else:
        nemeses = None
    butterfly = max(names, key=lambda n: (friends[n], reach[n]))
    if friends[butterfly] > 1:
        lines.append(f"The social butterfly is {_named(butterfly)[1]}, with {friends[butterfly]} friends.")
    loners = [_named(n)[1] for n in names if reach[n] < STRANGERS_BELOW]
    if loners:
        lines.append(f"{_capital(_and(loners))} {'talks' if len(loners) == 1 else 'talk'} to no one.")
    meter, purifier = _where(placements, "zytemp", end), _where(placements, "blueair", end)
    if meter and purifier:
        home_life = f"together in the {meter.room}" if meter.room == purifier.room else f"apart, in the {meter.room} and the {purifier.room}"
        text = f"The meter and the purifier live {home_life}"
        if (r := ties.get(("temperature", "blueair_temperature"))) is not None:
            mood = "agree" if r >= FRIENDS_AT else "disagree" if r <= -FRIENDS_AT else "barely speak"
            text += f"; their temperatures {mood} (r = {r:+.2f})"
        lines.append(text + ".")
    edges = sorted(({"a": a, "b": b, "r": r} for (a, b), r in ties.items() if abs(r) >= FRIENDS_AT), key=lambda e: -abs(e["r"]))
    return {
        "id": "society",
        "title": "The sensor society",
        "headline": f"{_named(soulmates[0])[0]} ♥ {_named(soulmates[1])[0]}" if soulmates else "A quiet party",
        "body": " ".join(lines),
        "members": [{"id": n, "label": _named(n)[0], "group": _named(n)[2], "friends": friends[n]} for n in names],
        "edges": edges[:40],
        "soulmates": list(soulmates) if soulmates else None,
        "nemeses": list(nemeses) if nemeses else None,
    }


def _key(midis: list[int]) -> tuple[int, str]:
    """The key ``(tonic pitch class, mode)`` that the notes fit best, by the Krumhansl-Schmuckler method."""
    counts = [0] * 12
    for m in midis:
        counts[m % 12] += 1

    def fit(key):
        tonic, mode = key
        profile = lore.MAJOR_PROFILE if mode == "major" else lore.MINOR_PROFILE
        return _pearson(counts, [profile[(i - tonic) % 12] for i in range(12)]) or -1.0

    return max(((tonic, mode) for tonic in range(12) for mode in ("major", "minor")), key=fit)


def _tonic(guests: dict[str, list]) -> int | None:
    """The home note of the household's rhythms: each guest at the centre of mass of its spectrum, all raised
    by the same number of octaves, and the key they fit best."""
    centroids = {}
    for name, points in guests.items():
        span = points[-1][0] - points[0][0]
        if len(points) < 32 or span < 3600:
            continue
        power = [abs(x) ** 2 for x in _fft(_detrend(_resample(points, CHOIR_POINTS)))[1 : CHOIR_POINTS // 2]]
        if sum(power) > 0:
            centroids[name] = sum(k * p for k, p in enumerate(power, 1)) / sum(power) / span
    if not centroids:
        return None
    octaves = round(math.log2(MIDDLE_C / statistics.median(centroids.values())))
    return _key([round(69 + 12 * math.log2(hz * 2**octaves / 440)) for hz in centroids.values()])[0]


def _unit(name: str) -> str:
    return next(unit for suffix, unit in UNITS.items() if name.endswith(suffix))


def _amount(value: float, unit: str) -> str:
    digits = 1 if unit in ("°C", "m/s", "mm/h") else 0
    return f"{value:.{digits}f} {unit}" if unit != "%" else f"{value:.0f}%"


def _now(name: str, points: list[tuple[float, float]]) -> float:
    """The guest over the last hour: its mean, or for the rain, how much fell."""
    recent = [v for t, v in points if t >= points[-1][0] - NOW_SECONDS]
    return sum(recent) * 3600 / NOW_SECONDS if name == "outdoor_rain" else statistics.fmean(recent)


def _distress(name: str, value: float) -> float:
    """0 where the guest is comfortable, rising to 1 where it is unbearable."""
    low, high, width, _ = COMFORT[name]
    return min(1.0, max(low - value, value - high, 0) / width)


def _cells(points: list[tuple[float, float]], n: int, rate: bool = False) -> list[float]:
    """``points`` in ``n`` equal cells across their span: each cell's mean, or with ``rate`` its total an hour.
    An empty cell keeps the mean before it, or has no rate."""
    t0 = points[0][0]
    width = max((points[-1][0] - t0) / n, 300.0 if rate else 1e-9)
    sums, counts = [0.0] * n, [0] * n
    for t, v in points:
        i = min(n - 1, int((t - t0) / width))
        sums[i] += v
        counts[i] += 1
    out = []
    for s, c in zip(sums, counts):
        out.append(s * 3600 / width if rate else s / c if c else out[-1])
    return out


def _pitch(mode: int, tonic: int, octave: int, degree: int) -> int:
    """The MIDI note of a scale ``degree`` of ``mode`` on ``tonic``, counted from the tonic in ``octave``."""
    return 12 * (octave + 1) + tonic + lore.MODES[mode][1][degree % 7] + 12 * (degree // 7)


def _air(where: str, guests: dict[str, list]) -> dict | None:
    """How heavy the air is ``where`` ("inside" or "outside"), and the mode it sings in for that."""
    factors = []
    for name, points in guests.items():
        if name in COMFORT and (GUESTS[name][2] == "outdoor") == (where == "outside"):
            value = _now(name, points)
            label, _, group = GUESTS[name]
            factors.append({"id": name, "label": label, "group": group, "value": value, "unit": _unit(name), "distress": _distress(name, value)})
    if not factors:
        return None
    weight = {f["id"]: COMFORT[f["id"]][3] for f in factors}
    worst = max(factors, key=lambda f: f["distress"] * weight[f["id"]])
    mean = sum(f["distress"] * weight[f["id"]] for f in factors) / sum(weight.values())
    distress = 0.7 * worst["distress"] * weight[worst["id"]] + 0.3 * mean  # the worst of it dominates
    band = next(i for i, (top, _) in enumerate(BANDS) if distress < top)
    mode = min(6, int(distress * 7))
    return {
        "id": where,
        "distress": distress,
        "band": band,
        "band_name": BANDS[band][1],
        "mode": mode,
        "mode_name": lore.MODES[mode][0],
        "worst": worst["id"] if worst["distress"] > 0 else None,
        "factors": factors,
        "shift": -12 if band == 2 else 0,  # heavy air sinks an octave
    }


def _phrase(name: str, points: list, air: dict, tonic: int, rng) -> list[list[float]]:
    """``name``'s leitmotif, ``[beat, MIDI note, beats, loudness]`` for each note: the line it traced over the window."""
    theme, degree, octave, beats, step = THEMES[name]
    mode, shift = air["mode"], air["shift"]
    loud = 0.55 + 0.45 * _distress(name, _now(name, points)) if name in COMFORT else 0.6  # who suffers most sings loudest
    notes = []
    if theme == "ground":  # the fan's ostinato, a pulse a beat for each step of its speed, on the tonic and the fifth below
        for i, speed in enumerate(_cells(points, round(PHRASE_BEATS / beats))):
            pulses = max(0, min(3, round(speed)))
            for j in range(pulses):
                notes.append([i * beats + j * beats / pulses, _pitch(mode, tonic, octave, 0 if j % 2 == 0 else -3), 0.8 * beats / pulses, loud])
    elif theme == "harp":  # the wind plucks the harmonics of the tonic, more and higher as it blows harder
        for i, speed in enumerate(_cells(points, PHRASE_BEATS)):
            plucks = max(0, min(4, round(speed / 1.5)))
            for j in range(plucks):
                harmonic = rng.randint(2, min(12, 3 + round(speed * 2)))
                notes.append([i + j / plucks, 12 * (octave + 1) + tonic + 12 * math.log2(harmonic), 3, 0.3 + 0.05 * min(speed, 8)])
    elif theme == "rain":  # a drop for every two-thirds of a millimetre an hour, on the mode's pentatonic notes
        for i, mm in enumerate(_cells(points, PHRASE_BEATS, rate=True)):
            for _ in range(max(0, min(6, round(mm * 1.5)))):
                notes.append([i + rng.random(), _pitch(mode, tonic, octave, rng.choice((0, 1, 2, 4, 5))) + shift, 0.25, 0.4])
    else:  # a melody that rises a scale step for every ``step`` the guest rose
        values = _cells(points, round(PHRASE_BEATS / beats))
        centre = statistics.fmean(values)
        length = beats * (0.4 if theme == "dust" else 1)
        for i, v in enumerate(values):
            notes.append([i * beats, _pitch(mode, tonic, octave, degree + max(-5, min(5, round((v - centre) / step)))) + shift, length, loud])
    return sorted(notes)


def choir(guests: dict[str, list]) -> dict | None:
    """The household sings its air: each guest a leitmotif tracing its own line, inside and outside each in the mode
    their comfort earns, on the tonic of the household's rhythms."""
    airs = {where: air for where in ("inside", "outside") if (air := _air(where, guests))}
    voiced = [name for name in GUESTS if name in guests and name in THEMES]
    if not voiced:
        return None
    for where in ("inside", "outside"):  # a fan or the rain alone still sings, in the plainest mode
        if where not in airs and any((GUESTS[n][2] == "outdoor") == (where == "outside") for n in voiced):
            airs[where] = {"id": where, "distress": 0.0, "band": 0, "band_name": BANDS[0][1], "mode": 1, "mode_name": "Ionian", "worst": None, "factors": [], "shift": 0}
    earth_hz = SCHUMANN_HZ * 2**EARTH_OCTAVES
    earth_pitch = 69 + 12 * math.log2(earth_hz / 440)
    found = _tonic(guests)
    tonic = round(earth_pitch) % 12 if found is None else found
    for air in airs.values():
        spelling = lore.MAJOR_KEYS if air["mode"] <= 2 else lore.MINOR_KEYS
        air["key"] = f"{spelling[tonic]} {air['mode_name']}"
    inside, outside = airs.get("inside"), airs.get("outside")

    # The house sings first, then the world, then both; a lone side sings its phrase twice. Each ends on its chord.
    if inside and outside:
        sections = [("The house", "inside"), ("The world", "outside"), ("Together", None)]
    else:
        sections = [("The house" if inside else "The world", None), ("Again", None)]
    rng = random.Random(_seed("choir", round(max(p[-1][0] for p in guests.values()) / 3600)))
    themes = []
    for name in voiced:
        where = "outside" if GUESTS[name][2] == "outdoor" else "inside"
        phrase = _phrase(name, guests[name], airs[where], tonic, rng)
        notes = [[s * PHRASE_BEATS + b, m, d, v] for s, (_, sings) in enumerate(sections) if sings in (where, None) for b, m, d, v in phrase]
        value = _now(name, guests[name])
        themes.append(
            {
                "id": name,
                "label": GUESTS[name][0],
                "group": GUESTS[name][2],
                "layer": where,
                "theme": THEMES[name][0],
                "value": value,
                "unit": _unit(name),
                "distress": _distress(name, value) if name in COMFORT else None,
                "notes": notes,
            }
        )
    end = len(sections) * PHRASE_BEATS
    for air in airs.values():
        chord = [_pitch(air["mode"], tonic, 3, d) + air["shift"] for d in (0, 4, 7, 9)]  # tonic, fifth, octave, tenth
        themes.append(
            {
                "id": f"chord_{air['id']}",
                "label": "The house's chord" if air["id"] == "inside" else "The world's chord",
                "group": "sky" if air["id"] == "inside" else "outdoor",
                "layer": air["id"],
                "theme": "chord",
                "value": None,
                "unit": "",
                "distress": None,
                "notes": [[end, m, CADENCE_BEATS, 0.5] for m in chord],
            }
        )

    d_in = inside["distress"] if inside else 0.0
    d_out = outside["distress"] if outside else 0.0
    bpm = round(88 - 30 * d_in - 10 * d_out)
    _, marking, gloss = next(t for t in lore.TEMPI if bpm < t[0])
    if inside and outside:
        mood, reading = MOODS[inside["band"]][outside["band"]]
    else:
        mood, reading = MOODS_ALONE[(inside or outside)["band"]]
    home = inside or outside
    earth = {
        "hz": earth_hz,
        "note": lore.NOTES[round(earth_pitch) % 12],
        "cents": (earth_pitch - round(earth_pitch)) * 100,
        "in_key": (round(earth_pitch) - tonic) % 12 in lore.MODES[home["mode"]][1],
    }

    lines = [reading]
    for air, where in ((inside, "Inside"), (outside, "Outside")):
        if air and air["factors"]:
            worst = next((f for f in air["factors"] if f["id"] == air["worst"]), None)
            weighs = f"{GUESTS[worst['id']][1]} weighs most, at {_amount(worst['value'], worst['unit'])}" if worst else "nothing weighs on it"
            lines.append(f"{where}, the air is {air['band_name']}: {weighs}.")
    if inside:
        lines.append(f"So the house sings in {inside['key']}. {lore.MODES[inside['mode']][2]}")
    if outside:
        if not inside:
            lines.append(f"The world sings in {outside['key']}. {lore.MODES[outside['mode']][2]}")
        elif outside["mode"] == inside["mode"]:
            lines.append("The world answers in the same mode: the two airs agree.")
        else:
            lines.append(f"The world answers in {outside['key']}. {lore.MODES[outside['mode']][2]}")
            apart = len(set(lore.MODES[inside["mode"]][1]) ^ set(lore.MODES[outside["mode"]][1])) // 2
            lines.append(
                f"They differ in {apart} of seven notes"
                + (", so the two final chords clash, as bitonal as Stravinsky's Petrushka." if apart >= 3 else ".")
            )
    lines.append(f"{marking}, {gloss}: {bpm} beats a minute.")
    suffering = [t for t in themes if t["distress"]]
    if suffering:
        loudest = max(suffering, key=lambda t: t["distress"])
        lines.append(f"Each guest sings its own leitmotif, tracing its line over the window; loudest is {GUESTS[loudest['id']][1]}, which suffers most.")
    by_id = {t["id"]: t for t in themes}
    if "blueair_fan_speed" in by_id and by_id["blueair_fan_speed"]["notes"]:
        lines.append("The purifier's fan keeps a ground bass, as in Purcell's lament for Dido.")
    if "outdoor_wind_speed" in by_id and by_id["outdoor_wind_speed"]["notes"]:
        lines.append("The wind strums an Aeolian harp, in the harmonic series, which belongs to no mode.")
    if "outdoor_rain" in by_id and (drops := len(by_id["outdoor_rain"]["notes"])):
        lines.append(f"The rain falls in {drops} drops, after Chopin's Raindrop prelude.")
    lines.append(
        f"The Earth hums {earth['note']} {earth['cents']:+.0f}¢, "
        + ("which the house's mode contains: the planet approves." if earth["in_key"] else "which the house's mode lacks: a cosmic dissonance.")
    )
    return {
        "id": "choir",
        "title": "The household choir",
        "headline": mood,
        "body": " ".join(lines),
        "mood": mood,
        "reading": reading,
        "key": home["key"],
        "tonic": tonic,
        "airs": list(airs.values()),
        "themes": themes,
        "sections": [{"label": label, "start": i * PHRASE_BEATS, "end": (i + 1) * PHRASE_BEATS} for i, (label, _) in enumerate(sections)],
        "beats": end + CADENCE_BEATS,
        "tempo": {"bpm": bpm, "marking": marking},
        "earth": earth,
    }


def souls(co2, placements=(), end: float | None = None) -> dict:
    """Occupants, from the CO2 balance V dC/dt = N g - Q (C - C_outdoor), with Q fitted over the window."""
    width = max(300.0, 2 * _median_step(co2))  # 5 minutes, unless the readings are sparser
    means = _bucket_means(co2, width)
    steps = [
        ((t0 + t1) / 2, (c0 + c1) / 2, (c1 - c0) / (t1 - t0) * 3600)
        for (t0, c0), (t1, c1) in zip(means, means[1:])
        if t1 - t0 <= 2 * width
    ]
    base = {"id": "souls", "title": "Souls present"}
    if len(steps) < 6:
        return {**base, "headline": "Counting…", "body": "Half an hour of breathing is needed to count the souls in it.", "souls": None, "spark": []}
    air_changes, fitted = ASSUMED_AIR_CHANGES, False
    if len(steps) >= 12:
        try:
            slope, _ = statistics.linear_regression([c for _, c, _ in steps], [d for _, _, d in steps])
        except statistics.StatisticsError:  # the CO2 never changed
            slope = 0.0
        if 0.05 < -slope < 5:
            air_changes, fitted = -slope, True
    placement = _where(placements, "zytemp", end if end is not None else steps[-1][0])
    room = placement.room if placement else None
    volume = ROOM_VOLUMES.get((room or "").lower(), DEFAULT_VOLUME)
    count = [(t, volume * (d + air_changes * (c - OUTDOOR_CO2)) / (1000 * EXHALED)) for t, c, d in steps]
    smooth = [(t, statistics.fmean(n for _, n in count[max(0, i - 5) : i + 1])) for i, (t, _) in enumerate(count)]
    now = smooth[-1][1]
    if -0.05 < now < 0:  # a hair below zero is nobody, not a negative soul
        now = 0.0
    peak_ts, peak = max(smooth, key=lambda s: s[1])
    reading = next(r for top, r in SOUL_READINGS if now < top)
    confession = "as the CO₂ itself confesses" if fitted else "a guess: the CO₂ would not say"
    return {
        **base,
        "headline": f"{now:.1f} soul{'' if round(now, 1) == 1 else 's'}",
        "body": f"{reading} Counted from how fast the CO₂ climbs, if each soul breathes out {EXHALED:.0f} L of CO₂ an hour "
        f"into {'a ' + room if room else 'a room'} of {volume:.0f} m³ that trades its air {air_changes:.2f} times an hour "
        f"({confession}). The most crowded moment: {peak:.1f} souls at {_clock(peak_ts)}.",
        "souls": now,
        "peak": peak,
        "peak_ts": peak_ts,
        "air_changes": air_changes,
        "fitted": fitted,
        "volume": volume,
        "room": room,
        "spark": _downsample([n for _, n in smooth], 48),
    }


def _chinese_year_of(ts: float) -> tuple[str, str]:
    year = datetime.fromtimestamp(ts).year
    if ts < astro.chinese_new_year(year):
        year -= 1
    return lore.chinese_year(year)


def births(born: dict[str, float], end: float) -> dict | None:
    """Each member's birthday (its first reading ever), star sign, Chinese year and biorhythms today."""
    members = []
    for key, name in MEMBERS.items():
        if key not in born:
            continue
        age = (end - born[key]) / astro.DAY
        sign, glyph = astro.zodiac_sign(astro.sun_longitude(born[key]))
        element, animal = _chinese_year_of(born[key])
        rhythms = [
            {"cycle": cycle, "value": math.sin(2 * math.pi * age / days), "critical": min(age % (days / 2), days / 2 - age % (days / 2)) < 0.5}
            for cycle, days in BIORHYTHMS
        ]
        members.append(
            {"id": key, "name": name, "born": born[key], "age_days": age, "sign": sign, "glyph": glyph, "element": element, "animal": animal, "rhythms": rhythms}
        )
    if not members:
        return None
    if len({m["sign"] for m in members}) == 1:
        told = [f"{m['name']} on {_date(m['born'])}" for m in members]
        signs = f", all under {members[0]['sign']}" if len(members) > 1 else f" under {members[0]['sign']}"
    else:
        told = [f"{m['name']} on {_date(m['born'])} under {m['sign']}" for m in members]
        signs = ""
    told[0] = told[0].replace(" on ", " was born on ", 1)
    lines = [_capital(_and(told)) + signs + "."]
    years = {(m["element"], m["animal"]) for m in members}
    if len(years) == 1:
        element, animal = years.pop()
        if len(members) > 1:
            kind = f"{element} {'Oxen' if animal == 'Ox' else animal + 's'}"
            headline, lead = f"A family of {kind}", f"All are {kind}"
        else:
            headline, lead = f"A {element} {animal}", f"It is a {element} {animal}"
        if (element, animal) == ("Fire", "Horse"):
            lead += ", the sign whose last return, in 1966, cut Japan's births by a quarter"
        lines.append(lead + ".")
    else:
        lines.append(_capital(_and([f"{m['name']} is a {m['element']} {m['animal']}" for m in members])) + ".")
        headline = f"{len(members)} members"
    critical = []
    for m in members:
        if cycles := [r["cycle"] for r in m["rhythms"] if r["critical"]]:
            critical.append(f"{m['name']} ({_and(cycles)})")
    if critical:
        lines.append(f"Critical days today: {_and(critical)}.")
    compatibility = None
    if "zytemp" in born and "blueair" in born:
        apart = abs(born["zytemp"] - born["blueair"])
        compatibility = statistics.fmean((1 + math.cos(2 * math.pi * apart / astro.DAY / days)) / 2 for _, days in BIORHYTHMS)
        lines.append(f"The meter and the purifier are {compatibility:.0%} compatible, born {_duration(apart)} apart.")
    return {"id": "births", "title": "Birth certificates", "headline": headline, "body": " ".join(lines), "members": members, "compatibility": compatibility}


def _daily_peak(points) -> tuple[float, float] | None:
    """When the daily rhythm of ``points`` peaks, in seconds after midnight UTC, and the share of them it explains.

    Fits a 24-hour sinusoid plus a straight line by least squares.
    """
    w = 2 * math.pi / astro.DAY
    rows = [(1.0, (t - points[0][0]) / astro.DAY, math.cos(w * t), math.sin(w * t)) for t, _ in points]
    ys = [v for _, v in points]
    coef = _solve(rows, ys)
    total = statistics.pvariance(ys)
    if coef is None or not total:
        return None
    residual = statistics.pvariance([y - sum(c * x for c, x in zip(coef, row)) for row, y in zip(rows, ys)])
    return (math.atan2(coef[3], coef[2]) / w) % astro.DAY, max(0.0, 1 - residual / total)


def clock(guests: dict[str, list], start: float, end: float, home=None) -> dict | None:
    """Each guest on the 24-hour wheel at the solar time its daily rhythm peaks, under the planetary hours."""
    if not guests:
        return None
    lat, lon = home or (0.0, astro.zone_longitude(end))
    midnight = end // astro.DAY * astro.DAY  # UTC
    now = astro.solar_hours(end, lon)
    planets, young = [], []
    for name, points in guests.items():
        if points[-1][0] - points[0][0] < MIN_DAILY_SPAN:
            young.append(_named(name)[1])
        elif peak := _daily_peak(points):
            hour = astro.solar_hours(midnight + peak[0], lon)
            planets.append({"id": name, "hour": hour, "strength": peak[1], "clock": _clock(midnight + peak[0])})
    moon = (12 + 24 * astro.moon_phase(end)) % 24  # it culminates later than the Sun by its elongation
    for name, hour in (("sun", 12.0), ("moon", moon)):
        planets.append({"id": name, "hour": hour, "strength": 1.0, "clock": _clock(end - (now - hour) % 24 * 3600)})
    for p in planets:
        p.update(label=_named(p["id"])[0], group=_named(p["id"])[2], house=lore.house(p["hour"]))
    aspects = []
    for i, a in enumerate(planets):
        for b in planets[i + 1 :]:
            apart = abs(a["hour"] - b["hour"]) * 15 % 360
            apart = min(apart, 360 - apart)
            for kind, angle, orb, _ in ASPECTS:
                if abs(apart - angle) <= orb:
                    aspects.append({"a": a["id"], "b": b["id"], "kind": kind, "orb": abs(apart - angle)})
                    break
    hours = astro.planetary_hours(end, lat, lon)
    current = next((h for h in hours if h[0] <= end < h[1]), hours[-1])
    ruler = current[2]
    lines = [f"It is the hour of {_planet(ruler)} {astro.PLANET_GLYPHS[ruler]} until {_clock(current[1])}, on a day of {_planet(hours[0][2])}."]
    by_house: dict[int, list[dict]] = {}
    for p in sorted((p for p in planets if p["group"] != "sky"), key=lambda p: -p["strength"])[:3]:
        by_house.setdefault(p["house"], []).append(p)
    for house, residents in by_house.items():
        who = _and([f"{_named(p['id'])[1]} ({p['clock']})" for p in residents])
        verb = "culminates" if len(residents) == 1 else "culminate"
        lines.append(f"{_capital(who)} {verb} in the {_ordinal(house)} house, of {lore.HOUSES[house - 1]}.")
    for aspect in sorted((a for a in aspects if {a["a"], a["b"]} != {"sun", "moon"}), key=lambda a: a["orb"])[:2]:
        verb = next(v for kind, _, _, v in ASPECTS if kind == aspect["kind"])
        lines.append(f"{_capital(_named(aspect['a'])[1])} {verb} {_named(aspect['b'])[1]}.")
    if end - start < MIN_DAILY_SPAN:
        lines.append("Nobody has a daily rhythm in a window this short: widen it to a day to see where everyone culminates.")
    elif young:
        lines.append(f"{_capital(_and(young))} {'has' if len(young) == 1 else 'have'} not yet lived a full day here.")
    return {
        "id": "clock",
        "title": "The celestial clock",
        "headline": f"Hour of {_planet(ruler)}",
        "body": " ".join(lines),
        "planets": planets,
        "aspects": aspects,
        "hours": [{"start": astro.solar_hours(a, lon), "end": astro.solar_hours(b, lon), "ruler": p, "glyph": astro.PLANET_GLYPHS[p]} for a, b, p in hours],
        "now": now,
        "ruler": ruler,
        "until": current[1],
        "day_ruler": hours[0][2],
    }


def _qi_flow(regions: dict[str, list]) -> tuple[str, ...] | None:
    """``(first, last)``: the regions whose PM2.5 moves first and last, by the lag at which each pair agrees best.

    ``()`` when no region lags another; None with less than a day of readings.
    """
    stamps = sorted({round(t) for points in regions.values() for t, _ in points})
    if len(stamps) < MIN_CELLS:
        return None
    hours = range(stamps[0], stamps[-1] + 1, 3600)
    cells = {}
    for region in lore.ELEMENTS:
        by_time = {round(t): v for t, v in regions[region]}
        cells[region] = [by_time.get(h) for h in hours]
    lead = dict.fromkeys(lore.ELEMENTS, 0)
    names = list(lore.ELEMENTS)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if best := _best_lag(cells[a], cells[b], 3):
                lead[a] += best[0]
                lead[b] -= best[0]
    if not any(lead.values()):
        return ()
    return max(lead, key=lead.get), min(lead, key=lead.get)


def elements(regions: dict[str, list]) -> dict | None:
    """NEA's five regions as the five phases, weighed by their PM2.5, and which way the haze flows between them."""
    if not any(regions.values()):
        return None
    base = {"id": "elements", "title": "Five elements of the island", "elements": [], "excess": None, "colour": None}
    if any(len(regions.get(r) or ()) < 3 for r in lore.ELEMENTS):
        return {**base, "headline": "Incomplete", "body": "Not all five regions have spoken in this window; the elements wait for each other."}
    means = {r: statistics.fmean(v for _, v in regions[r]) for r in lore.ELEMENTS}
    total = sum(means.values())
    cycle = list(lore.GENERATES)  # Wood, Fire, Earth, Metal, Water
    entries = []
    for r in sorted(lore.ELEMENTS, key=lambda r: cycle.index(lore.ELEMENTS[r][0])):
        element, char, _ = lore.ELEMENTS[r]
        entries.append(
            {
                "region": r,
                "element": element,
                "char": char,
                "mean": means[r],
                "share": means[r] / total if total else 0.2,
                "generates": lore.GENERATES[element],
                "overcomes": lore.OVERCOMES[element],
                "verb": OVERCOME_VERBS[element],
            }
        )
    strong, weak = max(means, key=means.get), min(means, key=means.get)
    if means[strong] - means[weak] < 1:
        return {**base, "headline": "In balance", "body": "The five elements weigh exactly the same. Suspicious.", "elements": entries}
    excess = lore.ELEMENTS[strong][0]
    remedy = next(e for e, victim in lore.OVERCOMES.items() if victim == excess)
    colour = next(c for e, _, c in lore.ELEMENTS.values() if e == remedy)
    lines = [
        f"The island's haze is {means[strong] / total:.0%} {excess} ({strong}, {means[strong]:.0f} µg/m³) "
        f"and only {means[weak] / total:.0%} {lore.ELEMENTS[weak][0]} ({weak}, {means[weak]:.0f}).",
        f"{excess} in excess {OVERCOME_VERBS[excess]} {lore.OVERCOMES[excess]}; {remedy} {OVERCOME_VERBS[remedy]} {excess}, so wear {colour}.",
    ]
    flow = _qi_flow(regions)
    if flow:
        first, last = flow
        lines.append(f"The qi enters through {lore.ELEMENTS[first][0]} ({first}) and pools in {lore.ELEMENTS[last][0]} ({last}).")
    elif flow == ():
        lines.append("The qi stands still: all five regions breathe in step.")
    return {
        **base,
        "headline": f"{excess} in excess",
        "body": " ".join(lines),
        "elements": entries,
        "dominant": strong,
        "weakest": weak,
        "excess": excess,
        "colour": colour,
        "flow": {"first": flow[0], "last": flow[1]} if flow else None,
    }


def winds(direction, speed=None, rain=None, haze=None) -> dict | None:
    """A rose of where the wind came from, on the eight trigrams, with the haze each wind carried, and the rain."""
    if not direction:
        return None
    speeds = dict(speed or [])
    haze = haze or []
    haze_times = [t for t, _ in haze]
    counts, fast, hazy, calm = [0] * 8, [[] for _ in range(8)], [[] for _ in range(8)], 0
    for t, degrees in direction:
        s = speeds.get(t)
        if s is not None and s < CALM:
            calm += 1
            continue
        i = int((degrees + 22.5) % 360 // 45)
        counts[i] += 1
        if s is not None:
            fast[i].append(s)
        if len(haze) > 1 and haze_times[0] <= t <= haze_times[-1]:
            hazy[i].append(_interpolate(haze, haze_times, t))
    total = len(direction)
    sectors = [
        {
            "abbr": abbr,
            "direction": name,
            "wind": greek,
            "trigram": list(lore.TRIGRAMS[trigram]),
            "lines": list(trigram),
            "share": counts[i] / total,
            "speed": statistics.fmean(fast[i]) if fast[i] else None,
            "haze": statistics.fmean(hazy[i]) if len(hazy[i]) >= 3 else None,
        }
        for i, (abbr, name, greek, trigram) in enumerate(lore.WINDS)
    ]
    lines = []
    prevailing = max(range(8), key=counts.__getitem__) if any(counts) else None
    if prevailing is None:
        headline = "Calm"
        lines.append("Not a breath of wind.")
    else:
        s = sectors[prevailing]
        name, image, glyph = s["trigram"]
        headline = f"{glyph} {s['wind']}"
        at = f", at {s['speed']:.1f} m/s" if s["speed"] else ""
        lines.append(f"The wind blew mostly from the {s['direction']} ({s['share']:.0%} of the time{at}): {s['wind']}, whose trigram is {name} {glyph}, {image}.")
    carried = [i for i in range(8) if sectors[i]["haze"] is not None]
    haziest = max(carried, key=lambda i: sectors[i]["haze"]) if carried else None
    if haziest is not None and haziest == prevailing:
        lines.append(f"It carried the thickest haze too, at {sectors[haziest]['haze']:.0f} µg/m³.")
    elif haziest is not None:
        s = sectors[haziest]
        lines.append(f"The haze rode in thickest from the {s['direction']} ({s['wind']}, {s['trigram'][2]}), at {s['haze']:.0f} µg/m³.")
    if calm:
        lines.append(f"The winds slept {calm / total:.0%} of the time.")
    rain_mm = None
    if rain:
        rain_mm = sum(v for _, v in rain)
        if rain_mm > 0:
            lines.append(f"The heavens wept {rain_mm:.1f} mm, hardest at {_clock(max(rain, key=lambda p: p[1])[0])}.")
        else:
            lines.append("The heavens shed no tears.")
    return {
        "id": "winds",
        "title": "The winds",
        "headline": headline,
        "body": " ".join(lines),
        "sectors": sectors,
        "calm": calm / total,
        "prevailing": prevailing,
        "haziest": haziest,
        "rain_mm": rain_mm,
    }


def ward(indoor, outdoor, placements=(), end: float | None = None) -> dict | None:
    """How much of the outdoor PM2.5 the purifier's room keeps out, hour by hour, and how late the rest arrives."""
    if not indoor or not outdoor:
        return None
    times = [t for t, _ in indoor]
    hours = []  # (ts, outdoor, indoor) for each of NEA's hours with the purifier reporting through it
    for t, out in outdoor:
        a, b = bisect.bisect_left(times, t - 1800), bisect.bisect_left(times, t + 1800)
        if b - a >= 3:
            hours.append((t, out, statistics.fmean(v for _, v in indoor[a:b])))
    base = {"id": "ward", "title": "The ward"}
    if len(hours) < 3:
        return {**base, "headline": "Unmeasured", "body": "The ward needs three hours of haze and purifier together.", "strength": None}
    outside = statistics.fmean(o for _, o, _ in hours)
    inside = statistics.fmean(i for _, _, i in hours)
    strength = 1 - inside / outside if outside else 0.0
    _, band, band_name = next(b for b in PM25_BANDS if outside <= b[0])
    indoors = {round(t): i for t, _, i in hours}
    delays = []
    for lag in range(5):
        matched = [(o, indoors[round(t) + lag * 3600]) for t, o, _ in hours if round(t) + lag * 3600 in indoors]
        if len(matched) >= 8 and (r := _pearson([o for o, _ in matched], [i for _, i in matched])) is not None:
            delays.append((r, -lag))
    lag = -max(delays)[1] if delays else None
    placement = _where(placements, "blueair", end if end is not None else hours[-1][0])
    room = f"the {placement.room}" if placement else "the house"
    reading = next(r for low, r in WARDS if strength >= low)
    lines = [f"Outside, the haze averaged {outside:.0f} µg/m³ (band {band}, {band_name}); in {room}, the purifier counted {inside:.0f}."]
    lines.append(f"{reading[:-1]}: it holds back {strength:.0%} of the haze." if strength >= 0 else reading)
    if lag == 0:
        lines.append("The haze walks straight in, within the hour.")
    elif lag:
        lines.append(f"The haze takes {lag} h to get past the walls.")
    breaches = sum(i > o for _, o, i in hours)
    lines.append(f"{breaches} of {len(hours)} hours were an inside job, with more particles in than out." if breaches else "Not one hour was an inside job.")
    return {
        **base,
        "headline": f"{strength:.0%} ward" if strength >= 0 else "Breached",
        "body": " ".join(lines),
        "strength": strength,
        "outdoor": outside,
        "indoor": inside,
        "band": band,
        "lag_h": lag,
        "breaches": breaches,
        "hours": [[t, o, i] for t, o, i in hours[-240:]],
    }


def analyze(
    co2: list[tuple[float, float]],
    temperature: list[tuple[float, float]],
    start: float,
    end: float,
    signals: dict[str, list[tuple[float, float]]] | None = None,
    others: dict[str, list[tuple[float, float]]] | None = None,
    regions: dict[str, list[tuple[float, float]]] | None = None,
    placements=(),
    born: dict[str, float] | None = None,
    home: tuple[float, float] | None = None,
    recent: dict[str, list[tuple[float, float]]] | None = None,
    outdoor_pm25: float | None = None,
) -> dict:
    """The findings for the window from ``start`` to ``end``.

    All series are ``(ts, value)`` lists in time order. ``signals`` maps
    ``op_XX`` names to theirs; ``others`` holds the rest of the household
    under its GUESTS names, plus ``outdoor_wind_direction``; ``regions`` maps
    NEA's regions to their PM2.5. ``placements`` are the devices' moves in
    time order, ``born`` maps MEMBERS to their first reading ever, and
    ``home`` is ``(latitude, longitude)``, for solar time. ``recent`` holds
    the CASTERS' readings over the day before ``end``, so that the hexagram
    of the hour is the same in every window; without it, the window's are used.
    ``outdoor_pm25`` is the latest outdoor PM2.5, if known, so the advice does not open windows into haze.
    """
    others = others or {}
    pool = {"co2": co2, "temperature": temperature, **others}
    guests = {name: pool[name] for name in GUESTS if len(pool.get(name) or ()) >= 2}
    findings = []
    if co2:
        findings += [
            aura(co2, temperature),
            lunar(co2, end),
            mercury(co2, start, end),
            chakra_residency(co2, outdoor_pm25),
            schumann(co2),
            golden_ratio(co2),
            numerology(co2),
            zodiac(co2, temperature, end),
            voices(signals or {}, co2, temperature, start, end),
        ]
    household = [
        iching(pool if recent is None else recent, end),
        society(guests, start, end, placements, home),
        choir(guests),
        souls(co2, placements, end) if co2 else None,
        births(born or {}, end),
        clock(guests, start, end, home),
        elements(regions or {}),
        winds(others.get("outdoor_wind_direction"), others.get("outdoor_wind_speed"), others.get("outdoor_rain"), others.get("outdoor_pm25")),
        ward(others.get("blueair_pm25"), others.get("outdoor_pm25"), placements, end),
    ]
    findings += [f for f in household if f]
    if co2:
        findings.append(horoscope(co2, end, findings, outdoor_pm25))
    if not findings:
        return {"findings": [], "disclaimer": "The Oracle needs readings to divine anything."}
    for f in findings:
        f["certainty"] = _pick(CERTAINTIES, f["id"], f["headline"])
    return {
        "findings": findings,
        "disclaimer": "Strictly pseudo-scientific. Every number is computed honestly; every conclusion is not.",
    }
