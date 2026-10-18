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
from .device import EXPLAINED

PHI = (1 + 5**0.5) / 2
SCHUMANN_HZ = 7.83
AIRING_PM25 = 35  # µg/m³ of outdoor PM2.5 (the US EPA 24-hour standard) above which airing trades CO2 for particles
STUFFY_PPM = 1000  # where a window is due
MAX_CO2 = 5000.0  # ppm; no prophecy sees the air thicker than this, where nobody should be breathing it


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
DAY_NUMBERS = {  # a personal day number -> (what the day is for, what the air asks of you on it)
    1: ("beginnings", "Begin something: a fresh measurement, or the meter in a new place."),
    2: ("partnership", "Pair up: set the meter beside the purifier and let them compare notes."),
    3: ("expression", "Express yourself: press Listen, and let the house sing."),
    4: ("work", "Do the chores: clean the purifier's pre-filter."),
    5: ("change", "Change something: move the furniture, so that the air takes a new path."),
    6: ("the home", "Tend the home: water the plants, which trade your CO₂ for oxygen."),
    7: ("reflection", "Sit still, and let the air settle."),
    8: ("power", "Use your power: run the purifier on high for an hour."),
    9: ("endings", "Finish things: replace what is worn out, the filter first."),
    11: ("intuition", "Trust your nose about the air today; it is a master's nose."),
    22: ("building", "Build something that lasts, such as the habit of checking the air."),
    33: ("teaching", "Teach someone to read a CO₂ meter."),
}

# Each sign's element and quality: Ptolemy's triplicities, and the cardinal, fixed and mutable signs.
SIGN_NATURES = {
    "Aries": ("fire", "cardinal"), "Taurus": ("earth", "fixed"), "Gemini": ("air", "mutable"),
    "Cancer": ("water", "cardinal"), "Leo": ("fire", "fixed"), "Virgo": ("earth", "mutable"),
    "Libra": ("air", "cardinal"), "Scorpio": ("water", "fixed"), "Sagittarius": ("fire", "mutable"),
    "Capricorn": ("earth", "cardinal"), "Aquarius": ("air", "fixed"), "Pisces": ("water", "mutable"),
}
ELEMENT_WAYS = {
    "fire": "flares up quickly and burns out as fast",
    "earth": "settles where it is put and stays",
    "air": "is doubly air, restless and talkative",
    "water": "runs deep and hides its currents",
}
QUALITY_WAYS = {"cardinal": "it starts things", "fixed": "it holds its ground", "mutable": "it changes its mind"}

AURAS = (  # (upper CO2 bound, name, hue, saturation %, reading, the colour opposite it on Goethe's circle, its CSS)
    (500, "Celestial White", 200, 15, "Pure, unburdened, possibly outdoors.", "black", "hsl(0 0% 16%)"),
    (650, "Azure", 205, 85, "Calm, clear, and well ventilated.", "orange", "hsl(28 90% 55%)"),
    (800, "Emerald", 150, 70, "Growth and healing. Plants would approve.", "rose", "hsl(335 70% 62%)"),
    (1000, "Golden", 45, 90, "Radiant and productive, for now.", "violet", "hsl(270 55% 58%)"),
    (1300, "Amber", 28, 90, "Passionate air with a hint of meeting room.", "blue", "hsl(212 80% 52%)"),
    (1800, "Crimson", 355, 75, "Intense. Concentration is high and dropping.", "green", "hsl(150 60% 40%)"),
    (math.inf, "Murky Brown", 25, 35, "The aura of a submarine at the end of a long patrol.", "slate blue", "hsl(212 35% 48%)"),
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
TRICKSTER = ("The Trickster", "It moves, but follows nothing we can measure. Perhaps something we cannot.")
CORRELATE_NAMES = {"co2": "CO\u2082", "temperature": "temperature", "time": "the passage of time", "moon": "the Moon"}
SIGNAL_FOLLOWS_AT = 0.6  # |r| needed to say a signal follows something
# Fewer readings than this in the window: a code the meter sends only at power-up, i.e. a setting or constant.
SIGNAL_MIN_POINTS = 10

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
SOLFEGE = ("do", "ra", "re", "me", "mi", "fa", "fi", "sol", "le", "la", "te", "ti")  # movable do, by semitones above the tonic

# Souls present
OUTDOOR_CO2 = 425.0  # ppm, the planet's background in 2026
EXHALED = 18.0  # litres of CO2 an adult at light seated work breathes out per hour (ASTM D6245's 0.0052 L/s at 1.2 met)
ROOM_VOLUMES = {"bedroom": 30, "living room": 60, "kitchen": 20, "study": 30, "office": 40}  # m³
DEFAULT_VOLUME = 40.0
ASSUMED_AIR_CHANGES = 0.5  # per hour, when the CO2 will not tell
CO2_DENSITY = 1.8  # g/L, at room temperature
SOUL_GRAMS = 21  # three-quarters of an ounce, what MacDougall's first dying patient lost, he said, as the soul left (1907)
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
PLANET_NATURES = {  # as Ptolemy has them (Tetrabiblos I.4–5); greater and lesser are the later astrologers' ranks
    "Saturn": "cold and dry, the greater malefic",
    "Jupiter": "temperate, the greater benefic",
    "Mars": "hot and dry, the lesser malefic",
    "Sun": "hot and dry",
    "Venus": "warm and moist, the lesser benefic",
    "Mercury": "now dry, now moist",
    "Moon": "moist",
}
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
WIND_GIFTS = {  # what the wind under each trigram brings, after the trigrams' attributes in Wilhelm
    "Qian": "strength, the Creative's",
    "Kun": "devotion, and dust",
    "Zhen": "movement, as thunder does",
    "Kan": "danger, and rain",
    "Gen": "rest, as a mountain does",
    "Xun": "a gentle wind that penetrates everything, haze included",
    "Li": "light, and smoke",
    "Dui": "joy, and damp",
}

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
COURSES = {  # a line -> what its caster does in the hour to come, and what the Moon does instead
    7: ("keeps rising", "keeps waxing"),
    9: ("turns to fall", "turns to wane"),
    8: ("keeps falling", "keeps waning"),
    6: ("turns to rise", "turns to wax"),
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


# ---------- foresight ----------
#
# Every method below also prophesies. A method that can say what a series will do next has a seer,
# ``foresee_<id>(points, ctx, now, times)``: the series up to ``now`` (in time order) and its context,
# ``ctx`` (the "target" series' name, the other "guests", NEA's "regions", the "wind_direction",
# the "placements", "home" and the window's "start"), give its value at each of ``times`` after
# ``now``, or None where the method is silent. The council in prophecy.py weighs them.


def _until(points, t: float):
    """The points up to ``t``, to ask a seer what it would have said then."""
    return points[: bisect.bisect_right(points, (t, math.inf))]


def _latest(points) -> float:
    """The air as it is now: the mean of its last ten minutes, or of its last two readings when they are sparser."""
    width = max(600.0, 2 * _median_step(points))
    return statistics.fmean(v for t, v in points if t >= points[-1][0] - width)


def _rate(points, seconds: float = 3600) -> float:
    """How fast ``points`` moved over their last ``seconds``, by least squares, per second."""
    recent = [(t, v) for t, v in points if t >= points[-1][0] - seconds]
    try:
        return statistics.linear_regression([t for t, _ in recent], [v for _, v in recent]).slope
    except statistics.StatisticsError:  # too few, or all at one moment
        return 0.0


def _plausible(ppm: float) -> float:
    """A foreseen CO2 within what air can be: not below the planet's own, nor beyond the meter's reach."""
    return min(max(ppm, OUTDOOR_CO2 - 25), MAX_CO2)


def _when(ts: float, now: float, word: str = "at") -> str:
    """``ts`` said from ``now``: "at 23:10", "at 03:00 tomorrow" or "on Oct 22"; or "by 23:10", "until Oct 22", …"""
    days = (datetime.fromtimestamp(ts).date() - datetime.fromtimestamp(now).date()).days
    if days > 1:
        return f"{'on' if word == 'at' else word} {_date(ts)}"
    return f"{word} {_clock(ts)}" + (" tomorrow" if days == 1 else "")


def _cells_before(points, now: float, step: float) -> list[float | None]:
    """The mean of ``points`` in each ``step``-long cell before ``now``, oldest first and the last ending at ``now``;
    None where a cell is empty."""
    n = int((now - points[0][0]) // step) + 1
    sums, counts = [0.0] * n, [0] * n
    for t, v in points:
        if 0 <= (k := int((now - t) // step)) < n:
            sums[n - 1 - k] += v
            counts[n - 1 - k] += 1
    return [s / c if c else None for s, c in zip(sums, counts)]


def _chain(states: list, n: int) -> list[list[float]]:
    """The chance of moving from each of ``n`` states to each other, from consecutive known ``states``;
    a state never left stays put."""
    counts = [[0] * n for _ in range(n)]
    for a, b in zip(states, states[1:]):
        if a is not None and b is not None:
            counts[a][b] += 1
    return [[c / sum(row) for c in row] if sum(row) else [float(i == j) for j in range(n)] for i, row in enumerate(counts)]


def _markov(cells: list, states: list, n: int, steps: int) -> list[tuple[list[float], float]] | None:
    """Where the chain of ``states`` (each cell's, out of ``n``) will stand after each of ``steps`` more cells:
    ``(chance of each state, expected value)``, the value of a state being the mean of its cells. None with too few."""
    if states[-1] is None or sum(s is not None for s in states) < 6:
        return None
    chain = _chain(states, n)
    seen: dict[int, list[float]] = {}
    for c, s in zip(cells, states):
        if s is not None:
            seen.setdefault(s, []).append(c)
    means = {s: statistics.fmean(vs) for s, vs in seen.items()}
    p, out = [float(i == states[-1]) for i in range(n)], []
    for _ in range(steps):
        p = [sum(p[i] * chain[i][j] for i in range(n)) for j in range(n)]
        out.append((p, sum(q * means[i] for i, q in enumerate(p) if q)))
    return out


def _long_run(walk: list[tuple[list[float], float]]) -> list[float]:
    """The share of its time the chain spends in each state, averaged over its whole ``walk``."""
    return [statistics.fmean(p[i] for p, _ in walk) for i in range(len(walk[0][0]))]


def _chakra_for(ppm: float):
    return next(c for c in CHAKRAS if ppm < c[0])


def chakra_of(ppm: float) -> str:
    return _chakra_for(ppm)[1]


def _chakra_walk(points, now: float, step: float, steps: int):
    """The kundalini's walk: the chakra of each ``step``-long cell, and where the chain of them leads next."""
    cells = _cells_before(points, now, step)
    states = [None if c is None else CHAKRAS.index(_chakra_for(c)) for c in cells]
    return states, _markov(cells, states, len(CHAKRAS), steps)


def _steps(points, times: list[float]) -> tuple[float, list[int]]:
    """A chain's cell length, from the spacing of ``times``, and how many cells after the last reading each of them is."""
    step = times[1] - times[0]
    return step, [max(1, math.ceil((t - points[-1][0]) / step)) for t in times]


def foresee_chakra(points, ctx, now, times):
    """The kundalini walks between the chakras as it has walked before: a Markov chain over the CO2 bands."""
    step, ahead = _steps(points, times)
    walk = _chakra_walk(points, points[-1][0], step, max(ahead))[1]
    return [walk[k - 1][1] for k in ahead] if walk else None


def _rises(a: int, b: int) -> str:
    """The kundalini's move from chakra ``a`` to ``b``: it rises toward the Crown as the air clears."""
    return "rest in" if a == b else "rise to" if b < a else "sink to"


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
    end = co2[-1][0]
    step = 3600 if end - co2[0][0] >= 12 * 3600 else 600
    states, walk = _chakra_walk(co2, end, step, 300)
    now = CHAKRAS.index(_chakra_for(_latest(co2)))
    prophecy = {}
    if walk:
        lead = lambda k: max(range(len(CHAKRAS)), key=walk[k][0].__getitem__)
        soon, later = lead(0), lead(5)
        within = "the hour" if step == 3600 else "ten minutes"
        prophecy["foretold"] = (
            f"Within {within} the kundalini will most likely {_rises(states[-1], soon)} {CHAKRAS[soon][1]} ({walk[0][0][soon]:.0%}); "
            f"{_when(end + 6 * step, end, word='by')}, {CHAKRAS[later][1]} ({walk[5][0][later]:.0%})."
        )
        karma = _long_run(walk)
        home = max(range(len(CHAKRAS)), key=karma.__getitem__)
        prophecy["revealed"] = (
            f"Its karma, the chain's long run: in the end the air will dwell {karma[home]:.0%} of its time in "
            f"{CHAKRAS[home][1]} ({CHAKRAS[home][2]}), however it wanders now."
        )
    if now:
        upper, name = CHAKRAS[now - 1][:2]
        prophecy["counsel"] = f"To raise the kundalini to {name}, bring the air below {upper} ppm. " + (
            airing(outdoor_pm25) if _latest(co2) >= 800 else "Breathe gently; it is nearly there."
        )
    else:
        prophecy["counsel"] = "The kundalini has reached the Crown. Change nothing, and breathe as little as is polite."
    return {
        "id": "chakra",
        "title": "Chakra residency",
        "headline": f"{CHAKRAS[dominant][1]} chakra",
        "body": f"Your air dwelt {counts[dominant] / total:.0%} of the time in {CHAKRAS[dominant][1]} "
        f"({CHAKRAS[dominant][2]}). {CHAKRAS[dominant][3].format(airing=airing(outdoor_pm25))}",
        "bands": bands,
        "prophecy": prophecy,
    }


def _aura_of(ppm: float):
    return next(a for a in AURAS if ppm < a[0])


def _hour_means(points) -> dict[int, float]:
    """Each hour of the day's mean, local time."""
    hours: dict[int, list[float]] = {}
    for t, v in points:
        hours.setdefault(datetime.fromtimestamp(t).hour, []).append(v)
    return {h: statistics.fmean(vs) for h, vs in hours.items()}


def aura(co2, temperature):
    mean = statistics.fmean(v for _, v in co2)
    _, name, hue, saturation, reading, complement, swatch = _aura_of(mean)
    temp_note = ""
    if temperature:
        t = statistics.fmean(v for _, v in temperature)
        if t >= 24:
            temp_note = " A warm halo suggests unresolved radiator energy."
        elif t <= 19:
            temp_note = " A cool rim suggests emotional draughts."
    flicker = _aura_of(statistics.fmean(v for t, v in co2 if t >= co2[-1][0] - 3600))[1]
    if flicker == name:
        foretold = f"The aura holds. Auras change slowly, so whatever the next hours bring, the air will keep returning to {mean:.0f} ppm, its {name} light."
    else:
        foretold = f"The aura flickers {flicker} this hour, but auras change slowly: the air will drift back to {mean:.0f} ppm, the {name} it has worn all window."
    prophecy = {
        "foretold": foretold,
        "counsel": f"To balance a {name} aura, wear its complement, {complement}: the eye, as Goethe found, demands the colour opposite the one it is shown.",
    }
    hours = _hour_means(co2)
    if len(hours) >= 6:
        bright, dim = min(hours, key=hours.get), max(hours, key=hours.get)
        prophecy["revealed"] = (
            f"The aura has its own day: it shines brightest at {bright:02d}:00, {_aura_of(hours[bright])[1]} at {hours[bright]:.0f} ppm, "
            f"and dims most at {dim:02d}:00, {_aura_of(hours[dim])[1]} at {hours[dim]:.0f}."
        )
    return {
        "id": "aura",
        "title": "Aura",
        "headline": name,
        "body": reading + temp_note,
        "hue": hue,
        "saturation": saturation,
        "complement": {"name": complement, "color": swatch},
        "prophecy": prophecy,
    }


def foresee_aura(points, ctx, now, times):
    """An aura is lasting: the air returns to its mean."""
    return [statistics.fmean(v for _, v in points)] * len(times)


LUNAR_DAYS = 7  # the Moon's phase only stands apart from the passage of time over a week or more


def _lunar_fit(points) -> tuple[float, float, float] | None:
    """``(level at the new moon, change at the full moon, r)`` of ``points`` against the Moon's illumination,
    by least squares; None if either is constant."""
    illum = [astro.moon_illumination(t) for t, _ in points]
    values = [v for _, v in points]
    if (r := _pearson(illum, values)) is None:
        return None
    slope, intercept = statistics.linear_regression(illum, values)
    return intercept, slope, r


def foresee_moon(points, ctx, now, times):
    """The air at each moment by its coupling to the Moon's illumination, once the Moon has had a week to show it."""
    if now - points[0][0] < LUNAR_DAYS * astro.DAY or (fit := _lunar_fit(points)) is None:
        return None
    level, change, _ = fit
    return [level + change * astro.moon_illumination(t) for t in times]


def lunar(co2, end):
    fit = _lunar_fit(co2)
    r = fit[2] if fit else None
    if r is None:
        coupling = "The Moon declined to comment: the window is too short for lunar resolution."
    elif abs(r) < 0.2:
        coupling = f"Lunar coupling r = {r:+.2f}. Your room is emotionally independent of the Moon."
    elif r > 0:
        coupling = f"Lunar coupling r = {r:+.2f}. Your CO2 waxes with the Moon. Werewolf-adjacent."
    else:
        coupling = f"Lunar coupling r = {r:+.2f}. Your room exhales as the Moon fills. Tidal ventilation."
    full, new = (next(t for t, k in astro.lunations(end, end + 31 * astro.DAY) if k == kind) for kind in ("full", "new"))
    foretold = f"The Moon will be full on {_date(full)} and new on {_date(new)}."
    if fit and end - co2[0][0] >= LUNAR_DAYS * astro.DAY:
        level, change, _ = fit
        foretold += f" By the coupling, your air will stand at {_plausible(level + change):.0f} ppm under the full moon and {_plausible(level):.0f} under the new."
        if abs(r) >= 0.2:
            lightest, when = ("full", full) if change < 0 else ("new", new)
            counsel = f"Hold your gatherings under the {lightest} moon, on {_date(when)}, when the coupling promises the lightest air."
        else:
            counsel = "The Moon has no claim on this room: plan your gatherings by the CO₂, not by the calendar."
        revealed = (
            f"The Moon lifts the seas twice a day; your room it {'lifts' if change > 0 else 'lowers'} by "
            f"{abs(change) / 100:.1f} ppm for every hundredth of its face it shows."
        )
    else:
        counsel = "The Moon will counsel only those who have listened to it for a week: widen the window."
        revealed = f"It is {astro.moon_age(end):.1f} days old, and will be full in {(full - end) / astro.DAY:.0f} days, when the air is said to turn strange."
    return {
        "id": "moon",
        "title": "Lunar influence",
        "headline": astro.moon_phase_name(end),
        "body": f"{astro.moon_illumination(end):.0%} illuminated, {astro.moon_age(end):.1f} days old. {coupling}",
        "phase": astro.moon_phase(end),
        "coupling": r,
        "prophecy": {"foretold": foretold, "counsel": counsel, "revealed": revealed},
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
    cycle = astro.mercury_cycle(end)
    shadow_start, retro, direct, shadow_end = cycle
    six = _grid(end, end + 6 * 3600, 24)
    carried = foresee_mercury(co2, {}, end, six, cycle)
    message = {
        "retrograde": "the last six hours' air back again, in reverse",
        "shadow": "half of yesterday's air and half of the last hours' in reverse",
        "direct": "yesterday's air again, hour for hour",
    }[_messenger(end, cycle)]
    foretold = f"Mercury the messenger carries {message}"
    if carried and carried[-1] is not None:
        foretold += f": {_plausible(carried[-1]):.0f} ppm {_when(six[-1], end, word='by')}."
    else:
        foretold += ", but this window holds too little of the past for him to carry."
    if retro_now:
        counsel = f"Until Mercury turns direct on {_date(direct)}, move no meter and sign nothing in a stuffy room: the air is going backwards."
    elif shadow and shadow[0] == "pre":
        counsel = f"Finish what needs finishing before {_date(retro)}: calibrate, back up the database, change the filter. Then, until {_date(direct)}, the air retraces its steps."
    elif shadow:
        counsel = f"Until {_date(shadow_end)}, redo what the retrograde undid: check the meter against fresh air, and the filter against its timer."
    else:
        counsel = f"Mercury walks free of his shadow until {_date(shadow_start)}: a fine time to begin new measurements."
    yesterday = [v for t, v in co2 if abs(t - (end - astro.DAY)) <= 900]
    if yesterday:
        revealed = f"Hermes keeps the roads between days: at this hour yesterday your air read {statistics.fmean(yesterday):.0f} ppm, and he remembers."
    else:
        revealed = "Hermes keeps the roads between days, but this window has not yet walked one: widen it past a day."
    return {
        "id": "mercury",
        "title": "Mercury",
        "headline": "Retrograde ℞" if retro_now else "Direct, in shadow" if shadow else "Direct",
        "body": body,
        "retrograde": retro_now,
        "shadow": {"kind": shadow[0], "start": shadow[1], "end": shadow[2]} if shadow else None,
        "cycle": dict(zip(("shadow_start", "retrograde", "direct", "shadow_end"), cycle)),
        "next_station": station,
        "next_turn": turn,
        "motion_deg_per_day": astro.mercury_motion(end),
        "prophecy": {"foretold": foretold, "counsel": counsel, "revealed": revealed},
    }


def _messenger(t: float, cycle) -> str:
    """What Mercury is doing at ``t``, by the ``cycle`` around it: "retrograde", "shadow" or "direct"."""
    shadow_start, retro, direct, shadow_end = cycle
    if retro <= t < direct:
        return "retrograde"
    return "shadow" if shadow_start <= t < shadow_end else "direct"


def foresee_mercury(points, ctx, now, times, cycle=None):
    """Mercury, the messenger, carries yesterday's air into today while direct, and brings the last hours' air back
    in reverse while retrograde; in his shadow, half of each."""
    cycle = cycle or astro.mercury_cycle(now)
    own = [t for t, _ in points]

    def at(t):
        return _interpolate(points, own, t) if len(points) > 1 and own[0] <= t <= own[-1] else None

    out = []
    for t in times:
        mirror, yesterday = at(2 * now - t), at(t - astro.DAY)
        doing = _messenger(t, cycle)
        both = [v for v in (yesterday, mirror) if v is not None]
        out.append(mirror if doing == "retrograde" else yesterday if doing == "direct" else statistics.fmean(both) if both else None)
    return out if any(v is not None for v in out) else None


SCHUMANN_POINTS = 512  # a power of two, for the FFT


def _dominant(points) -> dict:
    """The strongest rhythm in ``points`` once their straight line is taken out, by the FFT: its period (s),
    amplitude and phase, and the level it swings about over its last period, to carry it on past the window."""
    n = SCHUMANN_POINTS
    values = _resample(points, n + 1)[:-1]  # n samples a whole window apart, so that whole cycles fall on whole bins
    slope, intercept = statistics.linear_regression(range(n), values)
    spectrum = _fft([complex(v - (slope * i + intercept)) for i, v in enumerate(values)])
    k = max(range(1, n // 2), key=lambda k: abs(spectrum[k]))
    period = (points[-1][0] - points[0][0]) / k
    return {
        "period": period,
        "amplitude": 2 * abs(spectrum[k]) / n,
        "phase": cmath.phase(spectrum[k]),
        "level": statistics.fmean(v for t, v in points if t >= points[-1][0] - period),
        "t0": points[0][0],
    }


def _rhythm_at(rhythm: dict, t: float) -> float:
    return rhythm["level"] + rhythm["amplitude"] * math.cos(2 * math.pi * (t - rhythm["t0"]) / rhythm["period"] + rhythm["phase"])


def _crest(rhythm: dict, after: float, trough: bool = False) -> float:
    """When the rhythm next crests (or bottoms out) after ``after``."""
    turns = (after - rhythm["t0"]) / rhythm["period"] + rhythm["phase"] / (2 * math.pi) - (0.5 if trough else 0)
    return rhythm["t0"] + rhythm["period"] * (math.ceil(turns) - rhythm["phase"] / (2 * math.pi) + (0.5 if trough else 0))


def foresee_schumann(points, ctx, now, times):
    """The room's strongest rhythm, sounding on: the Earth's heartbeat does not stop when the window ends."""
    if len(points) < 16 or now - points[0][0] < 600:
        return None
    rhythm = _dominant(points)
    return [_rhythm_at(rhythm, t) for t in times]


def _note(hz: float) -> str:
    midi = 69 + 12 * math.log2(hz / 440)
    return f"{lore.NOTES[round(midi) % 12]} {(midi - round(midi)) * 100:+.0f}¢"


def schumann(co2, outdoor_pm25: float | None = None):
    if len(co2) < 16 or co2[-1][0] - co2[0][0] < 600:
        return {
            "id": "schumann",
            "title": "Schumann alignment",
            "headline": "Listening…",
            "body": "At least ten minutes of air are needed to hear the Earth's heartbeat in it.",
            "cents": None,
        }
    rhythm = _dominant(co2)
    period = rhythm["period"]
    octaves = math.log2(SCHUMANN_HZ * period)
    sub_octave = round(octaves)
    cents = (sub_octave - octaves) * 1200
    period_text = _duration(period) if period < 48 * 3600 else f"{period / 86400:.1f} days"
    sharp = "sharp" if cents > 0 else "flat"
    end = co2[-1][0]
    crest, trough = _crest(rhythm, end), _crest(rhythm, end, trough=True)
    if abs(cents) < 15:
        counsel = "It is in tune with the planet. Change nothing; the Earth would take it personally."
    else:
        tuned = 2**sub_octave / SCHUMANN_HZ
        how = "let its crowd come and go" if hazy(outdoor_pm25) else "air it"
        counsel = f"To bring the room into tune, it must breathe once every {_duration(tuned)}, not {_duration(period)}: {how} on that rhythm."
    return {
        "id": "schumann",
        "title": "Schumann alignment",
        "headline": f"Sub-octave {sub_octave}",
        "body": f"Your room breathes once every {period_text}, which is the {_ordinal(sub_octave)} sub-octave of the "
        f"Earth's 7.83 Hz heartbeat, {abs(cents):.0f} cents {sharp}. "
        + ("Spiritually in tune." if abs(cents) < 15 else "A gentle retuning with an open window is advised."),
        "cents": cents,
        "period_s": period,
        "prophecy": {
            "foretold": f"Its breath crests next {_when(crest, end)}, near {_plausible(_rhythm_at(rhythm, crest)):.0f} ppm, "
            f"and bottoms out {_when(trough, end)}, near {_plausible(_rhythm_at(rhythm, trough)):.0f}.",
            "counsel": counsel,
            "revealed": f"Raised {sub_octave + EARTH_OCTAVES} octaves into hearing, your room hums {_note(2 ** (sub_octave + EARTH_OCTAVES) / period)}, "
            f"where the Earth hums {_note(SCHUMANN_HZ * 2**EARTH_OCTAVES)}: that is the room's own note.",
        },
    }


GOLDEN_TURN = 0.1  # share of the window's range the air must turn back by before its last extreme counts as a swing's end


def _smooth(points) -> list[tuple[float, float]]:
    w = max(1, len(points) // 50)
    return [(t, statistics.fmean(v for _, v in points[max(0, i - w) : i + w + 1])) for i, (t, _) in enumerate(points)]


def _pivots(points, threshold: float) -> list[tuple[float, float]]:
    """The zigzag's turning points: each extreme that the series then left by more than ``threshold``."""
    pivots, direction = [], 0
    high = low = points[0]
    for p in points[1:]:
        if direction >= 0 and p[1] > high[1]:
            high = p
        if direction <= 0 and p[1] < low[1]:
            low = p
        if direction >= 0 and high[1] - p[1] > threshold:
            pivots.append(high)
            direction, low = -1, p
        elif direction <= 0 and p[1] - low[1] > threshold:
            pivots.append(low)
            direction, high = 1, p
    return pivots


def _spiral(points, until: float) -> list[tuple[float, float]] | None:
    """The golden spiral's turns, from the last two pivots of ``points`` until past ``until``: each swing is 1/φ of
    the one before, as Fibonacci retracements have it, and the air rises φ times as long as it falls."""
    smooth = _smooth(points)
    values = [v for _, v in smooth]
    pivots = _pivots(smooth, GOLDEN_TURN * (max(values) - min(values)))
    if len(pivots) < 2:
        return None
    (t0, v0), (t1, v1) = pivots[-2:]
    turns, swing, span = [(t1, v1)], v1 - v0, t1 - t0
    while turns[-1][0] <= until and len(turns) < 64 and span > 0:
        swing = -swing / PHI
        span = span / PHI if swing < 0 else span * PHI
        turns.append((turns[-1][0] + span, turns[-1][1] + swing))
    return [(t0, v0)] + turns


def _along(turns, now: float, value: float, t: float) -> float:
    """The air at ``t`` on its way along the spiral's ``turns``, setting out from ``value`` at ``now``."""
    previous = (now, value)
    for turn in (p for p in turns if p[0] > now):
        if t <= turn[0]:
            eased = (1 - math.cos(math.pi * (t - previous[0]) / (turn[0] - previous[0]))) / 2
            return previous[1] + (turn[1] - previous[1]) * eased
        previous = turn
    return previous[1]


def foresee_golden(points, ctx, now, times):
    """The air follows the golden spiral from where it stands: Fibonacci retracements, swing by shrinking swing."""
    if len(points) < 8 or not (turns := _spiral(points, times[-1])):
        return None
    value = _latest(points)
    return [_along(turns, now, value, t) for t in times]


def golden_ratio(co2, outdoor_pm25: float | None = None):
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
    end = co2[-1][0]
    prophecy = {}
    if turns := _spiral(co2, end + 2 * astro.DAY):
        (t0, v0), (t1, v1) = turns[:2]
        swing = v1 - v0
        ahead = [p for p in turns if p[0] > end]
        prophecy["foretold"] = (
            f"Its last swing {'rose' if swing > 0 else 'fell'} from {v0:.0f} to {v1:.0f} ppm in {_duration(t1 - t0)}; the golden spiral "
            + (f"now carries it to {ahead[0][1]:.0f} ppm {_when(ahead[0][0], end, word='by')}, and " if ahead else "")
            + f"at last to rest at {v1 - swing / PHI**2:.0f}, the 38.2 % retracement."
        )
        crests = [p for i, p in enumerate(turns[1:], 1) if p[0] > end and p[1] > turns[i - 1][1]]
        if crests:
            act = "keep the purifier high and the crowd thin" if hazy(outdoor_pm25) else "air the room"
            prophecy["counsel"] = f"Trade with the spiral, as the Fibonacci traders do: its next crest comes {_when(crests[0][0], end)}, near {crests[0][1]:.0f} ppm; {act} then, and not at the troughs."
        if abs(swing) > 5:
            prophecy["revealed"] = (
                f"Each swing is 1/φ of the one before, like the chambers of a nautilus (whose spiral, Falbo measured, grows by nearer 1.33): "
                f"in {math.ceil(math.log(abs(swing) / 5, PHI))} more swings the air will move less than 5 ppm, and be still."
            )
    return {
        "id": "golden",
        "title": "Divine proportion",
        "headline": f"{attainment:.0%} golden",
        "body": body,
        "ratio": ratio,
        "attainment": attainment,
        "prophecy": prophecy,
    }


def _day_number(life_path: int, ts: float) -> int:
    """The air's personal day number: the date's digits added up, plus its life path, reduced."""
    return _digital_root(life_path + sum(int(d) for d in datetime.fromtimestamp(ts).strftime("%Y%m%d")))


def numerology(co2):
    mean = round(statistics.fmean(v for _, v in co2))
    number = _digital_root(mean)
    end = co2[-1][0]
    tomorrow = _day_number(number, end + astro.DAY)
    theme, counsel = DAY_NUMBERS[tomorrow]
    master = next((end + d * astro.DAY for d in range(2, 90) if _day_number(number, end + d * astro.DAY) in (11, 22, 33)), None)
    if master:
        n = _day_number(number, master)
        revealed = f"The next master day of your air falls on {_date(master)}, a {n}: a day of {DAY_NUMBERS[n][0]}, when numbers do not reduce and neither should you."
    else:
        revealed = "No master day falls in the next three months: your air walks among ordinary numbers."
    return {
        "id": "numerology",
        "title": "Life path number",
        "headline": str(number),
        "body": f"Mean {mean} ppm reduces to {number}. {LIFE_PATHS[number]}",
        "number": number,
        "prophecy": {
            "foretold": f"Tomorrow, {_date(end + astro.DAY)}, is a {tomorrow} day for your air: a day of {theme}.",
            "counsel": counsel,
            "revealed": revealed,
        },
    }


def _harmony(mean: float, sun: float) -> tuple[int, str]:
    """The ppm nearest ``mean`` (and below 1000, where possible) that, read as degrees, trines or sextiles the Sun."""
    candidates = [
        (round((sun + sign * angle) % 360 + 360 * k), name)
        for angle, name in ((120, "trine"), (60, "sextile"))
        for sign in (1, -1)
        for k in range(1, 6)
    ]
    breathable = [c for c in candidates if OUTDOOR_CO2 < c[0] < STUFFY_PPM] or [c for c in candidates if c[0] > OUTDOOR_CO2]
    return min(breathable, key=lambda c: abs(c[0] - mean))


def zodiac(co2, temperature, end):
    sun_at = astro.sun_longitude(end)
    sun, sun_glyph = astro.zodiac_sign(sun_at)
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
    ingress = astro.sun_reaches((sun_at // 30 + 1) * 30, end)
    birthday = astro.sun_reaches(mean_co2 % 360, end)
    target, aspect = _harmony(mean_co2, sun_at)
    element, quality = SIGN_NATURES[rising]
    return {
        "id": "zodiac",
        "title": "Natal chart of your air",
        "headline": f"{sun}, {rising} rising",
        "body": " · ".join(f"{l['role']} in {l['sign']}" for l in lines),
        "signs": lines,
        "prophecy": {
            "foretold": f"The Sun enters {astro.zodiac_sign(sun_at + 30)[0]} {_when(ingress, end)}, and on {_date(birthday)} reaches "
            f"{mean_co2 % 30:.0f}° {rising}, your air's rising degree: its solar return, its birthday in the sky.",
            "counsel": f"To bring your air into {aspect} with the Sun, hold it at {target} ppm.",
            "revealed": f"{rising} is a {quality} {element} sign: your air {ELEMENT_WAYS[element]}, and {QUALITY_WAYS[quality]}.",
        },
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
    tomorrow = end + astro.DAY
    mercury_then = "retrograde" if astro.mercury_is_retrograde(tomorrow) else "in his shadow" if astro.mercury_shadow(tomorrow) else "direct"
    ruler = astro.DAY_RULERS[datetime.fromtimestamp(tomorrow).weekday()]
    phase = astro.moon_phase_name(tomorrow)
    return {
        "id": "horoscope",
        "title": "Today's horoscope",
        "headline": datetime.fromtimestamp(end).strftime("%A, %B %-d"),
        "body": " ".join([opening, middle, *omens, advice, f"Lucky ppm: {lucky}."]),
        "prophecy": {
            "foretold": f"Tomorrow is a day of {_planet(ruler)}, under a {phase if phase.endswith('Moon') else phase + ' Moon'}, with Mercury {mercury_then}.",
        },
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
    """The meter's still-unexplained codes that move, each identified by what it moves with, then spiritually."""
    signals = {
        name: points
        for name, points in signals.items()
        if name not in EXPLAINED
        and len(points) >= SIGNAL_MIN_POINTS
        and min(v for _, v in points) != max(v for _, v in points)
    }
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
        if best is not None and abs(known[best]) >= SIGNAL_FOLLOWS_AT:
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
                "follows": best if persona != TRICKSTER[0] else None,
                "spark": _downsample(values, 48),
            }
        )
    followers = sum(e["follows"] is not None for e in entries)
    prophet = _prophet(signals, co2)
    if prophet:
        op, lag, r, then = prophet
        foretold = f"The voice 0x{op.removeprefix('op_')} speaks {_duration(lag)} before your breath does (r = {r:+.2f}): by its word, your CO₂ will be {_plausible(then[1]):.0f} ppm {_when(then[0], end)}."
        counsel = f"Heed 0x{op.removeprefix('op_')}: when it stirs, the breath follows {_duration(lag)} later, before the meter admits it."
    else:
        foretold = "None of the voices speaks before your breath does: they only echo it, or answer to nothing."
        counsel = "Trust the meter's own reading; the voices know no more than it does."
    loudest = max(entries, key=lambda e: (e["max"] - e["min"]) / max(1.0, abs(e["favourite"])))
    return {
        "id": "signals",
        "title": "Voices in the wire",
        "headline": f"{len(entries)} unexplained signal{'s' if len(entries) != 1 else ''}",
        "body": f"The meter whispers {len(entries)} numbers its makers never explained. "
        f"{followers} of them follow something we can measure; the rest answer to forces unknown.",
        "signals": entries,
        "prophecy": {
            "foretold": foretold,
            "counsel": counsel,
            "revealed": f"Raudive heard the dead in radio static; the meter's static holds {len(entries)} voices, and the most restless is "
            f"{loudest['op']}, {loudest['persona']}, whose favourite number {loudest['favourite']} is {loudest['favourite']:X} in the hexadecimal the meter thinks in.",
        },
    }


PROPHET_CELL = 60  # seconds: the voices are heard minute by minute
PROPHET_LAG = 30  # cells: how far ahead of the breath a voice may speak


def _prophet(signals: dict, co2) -> tuple[str, float, float, tuple[float, float]] | None:
    """The voice whose moves your CO2 repeats soonest after, if any: ``(op, lead in s, r, (when, CO2 then))``,
    the CO2 then by regressing it on the voice's reading that much earlier."""
    end = co2[-1][0]
    grid = _grid(max(co2[0][0], end - 6 * 3600), end, max(MIN_CELLS, round(min(end - co2[0][0], 6 * 3600) / PROPHET_CELL)))
    step = grid[1] - grid[0]
    breath = _on_grid(co2, grid, 3 * step)
    best = None
    for op, points in signals.items():
        voice = _on_grid(points, grid, 3 * step)
        for lag in range(1, PROPHET_LAG + 1):
            if (r := _paired_pearson(voice, breath, lag)) is not None and abs(r) >= SIGNAL_FOLLOWS_AT and (best is None or abs(r) > abs(best[2])):
                best = (op, lag, r, voice)
    if best is None:
        return None
    op, lag, r, voice = best
    pairs = [(x, y) for x, y in zip(voice, breath[lag:]) if x is not None and y is not None]
    slope, intercept = statistics.linear_regression([x for x, _ in pairs], [y for _, y in pairs])
    said = next(v for v in reversed(voice) if v is not None)
    return op, lag * step, r, (end + lag * step, intercept + slope * said)


def _line(points, hour: float) -> tuple[int, float, float] | None:
    """The line ``points`` cast at ``hour``, how much they changed over the hour before it, and their usual hourly change.

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
    return ((9 if old else 7) if change > 0 else (6 if old else 8)), change, usual


def _turns(value: int) -> bool:
    """Whether a line of ``value`` will be yang once it has changed: old yin becomes yang, old yang yin."""
    return value in (6, 7)


def foresee_iching(points, ctx, now, times):
    """The hour goes where the hexagram turns: a line that moved over twice its usual change reverses, the others keep
    their course, each by its usual hourly change, for the hour the hexagram speaks for."""
    if not (cast := _line(points, now // 3600 * 3600)):
        return None
    value, change, usual = cast
    step = (usual or abs(change)) * (1 if _turns(value) else -1)
    here = _latest(points)
    return [here + step * min(1.0, (t - now) / 3600) for t in times]


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
                value, change, _ = cast
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
    courses = [
        f"{line['caster']} {COURSES[line['value']][line['caster'] == 'the Moon']}" + (" (by coins)" if line["coins"] else "")
        for line in lines
    ]
    turning = [line["caster"] for line in lines if line["changing"] and not line["coins"]]
    if becomes and becomes in JUDGEMENTS:
        counsel = JUDGEMENTS[becomes]
    elif turning:
        counsel = f"Act before the turn: {turning[0]} is about to reverse, and the hour with it."
    else:
        counsel = "Nothing turns this hour. Carry on as you are; the hexagram will keep."
    nuclear = lore.hexagram(yang[1:4] + yang[2:5])
    prophecy = {
        "foretold": f"In the hour to come, as the lines turn: {_and(courses)}.",
        "counsel": counsel,
        "revealed": f"Hidden in its four middle lines lies its nuclear hexagram, {nuclear}. {lore.HEXAGRAMS[nuclear - 1]}: the hour's secret heart.",
    }
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
        "prophecy": prophecy,
    }


def _sky_at(name: str, t: float, home) -> float:
    lat, lon = home or (0.0, astro.zone_longitude(t))
    return astro.sun_elevation(t, lat, lon) if name == "sun" else astro.moon_illumination(t)


def _seats(guests: dict[str, list], start: float, end: float, home=None) -> tuple[dict, list[float], float]:
    """Everyone on one grid of cells, ``(cells by guest, grid, cell length)``: the guests that move, and the Sun and
    the Moon once the window covers their cycle (over less, they would only stand in for the passage of time)."""
    grid = _grid(start, end, min(SOCIETY_CELLS[1], max(SOCIETY_CELLS[0], round((end - start) / CELL_SECONDS))))
    step = grid[1] - grid[0]
    seats = {}
    for name, points in guests.items():
        cells = _on_grid(points, grid, max(3 * _median_step(points), 2 * step))
        known = [c for c in cells if c is not None]
        if len(known) >= MIN_CELLS and min(known) < max(known):
            seats[name] = cells
    if seats and end - start >= astro.DAY:
        seats["sun"] = [_sky_at("sun", t, home) for t in grid]
    if seats and end - start >= 7 * astro.DAY:
        seats["moon"] = [_sky_at("moon", t, home) for t in grid]
    return seats, grid, step


def _follows(seats: dict, target: str, max_lag: int) -> tuple[str, int, float] | None:
    """Whom ``target`` follows: the guest whose moves its cells repeat most faithfully some cells later, ``(guest, lag, r)``."""
    best = None
    for name, cells in seats.items():
        for lag in range(1, max_lag + 1) if name != target else ():
            r = _paired_pearson(cells, seats[target], lag)
            if r is not None and abs(r) >= FRIENDS_AT and (best is None or abs(r) > abs(best[2])):
                best = (name, lag, r)
    return best


def foresee_society(points, ctx, now, times):
    """Your air does what its leader did a little before: the guest it follows best, by regression on it that many
    cells earlier. The Sun and the Moon lead from as far ahead as anyone likes; the others only as far as their lead."""
    target, home = ctx["target"], ctx.get("home")
    guests = {**ctx["guests"], target: points}
    seats, grid, step = _seats(guests, ctx["start"], now, home)
    if target not in seats or not (lead := _follows(seats, target, min(len(grid) // 6, max(1, round(3 * 3600 / step))))):
        return None
    foretell = _led_by(seats, guests, lead[0], target, lead[1] * step, step, home)
    return [foretell(t) for t in times]


def _led_by(seats: dict, guests: dict, leader: str, target: str, lead: float, step: float, home):
    """The target as its leader foretells it, a function of time: by regression on the leader ``lead`` seconds earlier."""
    lag = round(lead / step)
    pairs = [(x, y) for x, y in zip(seats[leader], seats[target][lag:]) if x is not None and y is not None]
    slope, intercept = statistics.linear_regression([x for x, _ in pairs], [y for _, y in pairs])
    points = guests.get(leader) or []
    own = [t for t, _ in points]

    def foretell(t):
        t -= lead
        if leader in SKY:
            return intercept + slope * _sky_at(leader, t, home)
        return intercept + slope * _interpolate(points, own, t) if own and own[0] <= t <= own[-1] else None

    return foretell


def society(guests: dict[str, list], start: float, end: float, placements=(), home=None) -> dict | None:
    """Everyone's correlation with everyone on one grid: who follows whom, and who talks to no one."""
    seats, grid, step = _seats(guests, start, end, home)
    if not seats:
        return None
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
    max_lag = min(len(grid) // 6, max(1, round(3 * 3600 / step)))
    prophecy = {}
    if lead := ("co2" in seats and _follows(seats, "co2", max_lag)):
        name, lag, r = lead
        ahead = end + lag * step
        foretold = _led_by(seats, guests, name, "co2", lag * step, step, home)(ahead)
        who = _named(name)[1]
        prophecy["foretold"] = f"Your CO₂ follows {who} by {_duration(lag * step)} (r = {r:+.2f})" + (
            f": by what {who} has already done, your CO₂ will be {_plausible(foretold):.0f} ppm {_when(ahead, end)}." if foretold is not None else "."
        )
        if _named(name)[2] in ("zytemp", "blueair"):
            prophecy["counsel"] = f"To steer your CO₂, steer {who}: what it does, your air does {_duration(lag * step)} later."
        else:
            prophecy["counsel"] = f"You cannot steer {who}, so heed it: when it moves, your air follows {_duration(lag * step)} later."
    elif "co2" in seats:
        prophecy["foretold"] = "Nobody leads your CO₂; it keeps its own counsel, and foretells nothing of itself."
        prophecy["counsel"] = "Steer your CO₂ yourself, then: nobody else will."
    leads = dict.fromkeys(names, 0)
    for e in edges:
        if (best := _best_lag(seats[e["a"]], seats[e["b"]], max_lag, 1 if e["r"] > 0 else -1)) and best[0]:
            leads[e["a"] if best[0] > 0 else e["b"]] += 1
    ruler = max(names, key=lambda n: (leads[n], reach[n]))
    if leads[ruler]:
        prophecy["revealed"] = (
            f"The household's true ruler is {_named(ruler)[1]}: {leads[ruler]} of the others "
            f"follow where it leads, a little later, whatever the household believes."
        )
    return {
        "id": "society",
        "title": "The sensor society",
        "headline": f"{_named(soulmates[0])[0]} ♥ {_named(soulmates[1])[0]}" if soulmates else "A quiet party",
        "body": " ".join(lines),
        "members": [{"id": n, "label": _named(n)[0], "group": _named(n)[2], "friends": friends[n]} for n in names],
        "edges": edges[:40],
        "soulmates": list(soulmates) if soulmates else None,
        "nemeses": list(nemeses) if nemeses else None,
        "prophecy": prophecy,
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
    return _air_of(where, factors) if factors else None


def _brighter(air: dict) -> tuple[str, float, int] | None:
    """What the air's worst guest must come to for it to sing a mode brighter: ``(guest, value, mode)``; None if even
    its comfort would not do it, another guest weighing as much."""
    if not air["mode"] or not air["worst"]:
        return None
    worst = next(f for f in air["factors"] if f["id"] == air["worst"])
    low, high = COMFORT[worst["id"]][:2]

    def mode_at(value):
        changed = {**worst, "value": value, "distress": _distress(worst["id"], value)}
        return _air_of(air["id"], [changed if f is worst else f for f in air["factors"]])["mode"]

    near, far = worst["value"], high if worst["value"] > high else low
    if mode_at(far) >= air["mode"]:
        return None
    for _ in range(40):  # bisect for the least change that does it
        middle = (near + far) / 2
        near, far = (near, middle) if mode_at(middle) < air["mode"] else (middle, far)
    return worst["id"], far, mode_at(far)


def foresee_choir(points, ctx, now, times):
    """Every phrase resolves to its tonic: the air returns to its mean, by a beat (an eighth of the window) at a time."""
    if (beat := (now - points[0][0]) / PHRASE_BEATS) <= 0:
        return None
    tonic, here = statistics.fmean(v for _, v in points), _latest(points)
    return [tonic + (here - tonic) * math.exp(-(t - now) / beat) for t in times]


def _air_of(where: str, factors: list[dict]) -> dict:
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
    prophecy = {}
    lead = next((n for n in ("co2", *voiced) if n in by_id and n in COMFORT), voiced[0])  # a melody, not a pulse
    points = guests[lead]
    last = points[-1][0]
    beat = (last - points[0][0]) / PHRASE_BEATS
    if beat > 0:
        tonic_value, here = statistics.fmean(v for _, v in points), _latest(points)
        unit = _unit(lead)
        prophecy["foretold"] = (
            f"Every phrase resolves to its tonic: {GUESTS[lead][1]}, at {_amount(here, unit)}, will settle toward "
            f"{_amount(tonic_value, unit)}, halfway home {_when(last + beat * math.log(2), last)}."
        )
    if inside and (lift := _brighter(inside)):
        name, value, mode = lift
        prophecy["counsel"] = f"To lift the house from {inside['mode_name']} to {lore.MODES[mode][0]}, bring {GUESTS[name][1]} to {_amount(value, _unit(name))}."
    elif inside and not inside["mode"]:
        prophecy["counsel"] = "The house sings in Lydian, the brightest of the modes: change nothing."
    phrase = [round(m) for b, m, _, _ in by_id[lead]["notes"] if b < PHRASE_BEATS]
    sung = [SOLFEGE[(m - tonic) % 12] for i, m in enumerate(phrase) if not i or m != phrase[i - 1]][:5]
    if len(sung) >= 2:
        kepler = "–".join(sung)
        prophecy["revealed"] = (
            f"Kepler heard the Earth sing mi–fa–mi, for misery and famine; {GUESTS[lead][1]} sings {kepler}"
            + (", the Earth's own song." if "mi–fa–mi" in kepler else ".")
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
        "prophecy": prophecy,
    }


def souls(co2, placements=(), end: float | None = None, outdoor_pm25: float | None = None) -> dict:
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
    last, here = co2[-1][0], _latest(co2)
    settle = _settles(max(0.0, now), air_changes, volume)
    allowed = (STUFFY_PPM - OUTDOOR_CO2) * air_changes * volume / (1000 * EXHALED)  # souls the room holds below 1000 ppm
    if now >= 0.05:
        foretold = f"If the {now:.1f} soul{'' if round(now, 1) == 1 else 's'} stay, the air settles at {_plausible(settle):.0f} ppm"
        if here < STUFFY_PPM < settle:
            hours = -math.log((STUFFY_PPM - settle) / (here - settle)) / air_changes
            foretold += f", crossing {STUFFY_PPM} ppm {_when(last + hours * 3600, last)}."
        else:
            foretold += f", nine-tenths of the way there {_when(last + math.log(10) / air_changes * 3600, last)}."
    else:
        foretold = f"With nobody breathing, the air sinks back toward the outdoor {OUTDOOR_CO2:.0f} ppm, halfway there {_when(last + math.log(2) / air_changes * 3600, last)}."
    if settle >= STUFFY_PPM:
        counsel = (
            f"For the air to stay under {STUFFY_PPM} ppm, at most {allowed:.1f} souls may stay, or the room must trade its air "
            f"{now * EXHALED * 1000 / ((STUFFY_PPM - OUTDOOR_CO2) * volume):.2f} times an hour, not {air_changes:.2f}."
        )
        if hazy(outdoor_pm25):
            counsel += " The haze is thick, so let souls leave rather than windows open."
    else:
        counsel = f"The room holds {allowed:.1f} souls below {STUFFY_PPM} ppm: there is room for {max(0.0, allowed - max(0.0, now)):.1f} more."
    grams = EXHALED * CO2_DENSITY
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
        "settles": settle,
        "allowed": allowed,
        "spark": _downsample([n for _, n in smooth], 48),
        "prophecy": {
            "foretold": foretold,
            "counsel": counsel,
            "revealed": f"MacDougall weighed a dying man's soul at {SOUL_GRAMS} grams; each soul here breathes out {grams:.0f} g of CO₂ an hour, "
            f"its own weight every {_duration(SOUL_GRAMS / grams * 3600)}.",
        },
    }


def _settles(souls: float, air_changes: float, volume: float) -> float:
    """The CO2 a room settles at with ``souls`` breathing in it: the outdoor air's, plus their breath over its ventilation."""
    return OUTDOOR_CO2 + souls * EXHALED * 1000 / (air_changes * volume)


def foresee_souls(points, ctx, now, times):
    """The CO2 balance carried forward: the souls now present breathe on, and the room trades its air as it has."""
    f = souls(points, ctx.get("placements", ()), now)
    if f["souls"] is None:
        return None
    settle, here = f["settles"], _latest(points)
    return [settle + (here - settle) * math.exp(-f["air_changes"] * (t - now) / 3600) for t in times]


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
    critical_next = []
    for m in members:
        when, cycle = min(((math.floor(m["age_days"] / (days / 2)) + 1) * days / 2, cycle) for cycle, days in BIORHYTHMS)
        critical_next.append(f"{m['name']} on {_date(born[m['id']] + when * astro.DAY)} ({cycle})")
    best = {m["id"]: _best_day(born[m["id"]], end) for m in members}
    chores = [f"{verb} on {_date(best[key])}" for key, verb in BEST_FOR.items() if key in best]
    prophecy = {
        "foretold": f"The next critical days: {_and(critical_next)}.",
        "counsel": _capital(_and(chores)) + ", at their peaks; and move no one on a critical day." if chores else "Move no one on a critical day.",
    }
    if "zytemp" in born and "blueair" in born:
        together = _best_day((born["zytemp"], born["blueair"]), end)
        prophecy["revealed"] = (
            f"Their rhythms keep the same distance for ever, so the meter and the purifier stay {compatibility:.0%} compatible; "
            f"their happiest day together falls on {_date(together)}."
        )
    return {
        "id": "births",
        "title": "Birth certificates",
        "headline": headline,
        "body": " ".join(lines),
        "members": members,
        "compatibility": compatibility,
        "prophecy": prophecy,
    }


BEST_FOR = {  # what to do on each member's best day
    "zytemp": "Calibrate the meter",
    "blueair": "change the purifier's filter",
    "island": "trust the island's PM2.5",
    "weather": "trust the forecast",
}


def _best_day(born, end: float, days: int = 33) -> float:
    """Of the next ``days`` noons after ``end``, the one when ``born``'s (one birthday or several) biorhythms add up highest."""
    births = born if isinstance(born, tuple) else (born,)
    noon = end // astro.DAY * astro.DAY + astro.DAY / 2
    return max(
        (noon + d * astro.DAY for d in range(1, days + 1)),
        key=lambda t: sum(math.sin(2 * math.pi * (t - b) / astro.DAY / period) for b in births for _, period in BIORHYTHMS),
    )


def _daily_fit(points) -> tuple[list[float], float] | None:
    """A 24-hour sinusoid plus a straight line through ``points``, by least squares: its coefficients (level at the
    first point, change a day, cosine and sine of the time of day) and the share of the variance it explains."""
    w = 2 * math.pi / astro.DAY
    rows = [(1.0, (t - points[0][0]) / astro.DAY, math.cos(w * t), math.sin(w * t)) for t, _ in points]
    ys = [v for _, v in points]
    coef = _solve(rows, ys)
    total = statistics.pvariance(ys)
    if coef is None or not total:
        return None
    residual = statistics.pvariance([y - sum(c * x for c, x in zip(coef, row)) for row, y in zip(rows, ys)])
    return coef, max(0.0, 1 - residual / total)


def _daily_peak(points) -> tuple[float, float] | None:
    """When the daily rhythm of ``points`` peaks, in seconds after midnight UTC, and the share of them it explains."""
    if not (fit := _daily_fit(points)):
        return None
    coef, explained = fit
    return (math.atan2(coef[3], coef[2]) / (2 * math.pi / astro.DAY)) % astro.DAY, explained


def _daily_at(points, coef, now: float, t: float) -> float:
    """The daily rhythm at ``t``, from the level its line had reached by ``now``."""
    w = 2 * math.pi / astro.DAY
    return coef[0] + coef[1] * (now - points[0][0]) / astro.DAY + coef[2] * math.cos(w * t) + coef[3] * math.sin(w * t)


def foresee_clock(points, ctx, now, times):
    """The daily rhythm turns on: each guest culminates tomorrow when it culminated today (a cosinor, in chronobiology)."""
    if now - points[0][0] < MIN_DAILY_SPAN or not (fit := _daily_fit(points)):
        return None
    return [_daily_at(points, fit[0], now, t) for t in times]


def _rulers(guests: dict, start: float, end: float, home) -> dict[str, tuple[str, float]]:
    """Each guest's ruling planet, in whose hours it stands highest: ``guest -> (planet, mean z-score in its hours)``."""
    lat, lon = home or (0.0, astro.zone_longitude(end))
    hours, t = [], start
    while t < end and len(hours) < 24 * 400:
        day = astro.planetary_hours(t, lat, lon)
        hours += [h for h in day if h[1] > t]
        t = day[-1][1] + 60  # into the next planetary day, clear of rounding at sunrise
    starts = [h[0] for h in hours]
    out = {}
    for name, points in guests.items():
        values = [v for _, v in points]
        if len(values) < 24 or not (spread := statistics.pstdev(values)):
            continue
        mean, by_planet = statistics.fmean(values), {}
        for t, v in points:
            if (i := bisect.bisect_right(starts, t) - 1) >= 0 and t < hours[i][1]:
                by_planet.setdefault(hours[i][2], []).append((v - mean) / spread)
        if len(by_planet) == len(astro.CHALDEAN):
            planet = max(by_planet, key=lambda p: statistics.fmean(by_planet[p]))
            out[name] = planet, statistics.fmean(by_planet[planet])
    return out


def clock(guests: dict[str, list], start: float, end: float, home=None, outdoor_pm25: float | None = None) -> dict | None:
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
    prophecy = {}
    rhythmic = [p for p in planets if p["group"] != "sky"]
    if rhythmic:
        lead = next((p for p in rhythmic if p["id"] == "co2"), max(rhythmic, key=lambda p: p["strength"]))
        points = guests[lead["id"]]
        coef = _daily_fit(points)[0]
        peak = (midnight + _daily_peak(points)[0] - end) % astro.DAY + end
        trough = (peak - astro.DAY / 2 - end) % astro.DAY + end
        unit = _unit(lead["id"])
        prophecy["foretold"] = (
            f"{_capital(_named(lead['id'])[1])} culminates next {_when(peak, end)}, near {_amount(_daily_at(points, coef, end, peak), unit)}, "
            f"and sinks lowest {_when(trough, end)}, near {_amount(_daily_at(points, coef, end, trough), unit)}."
        )
    rulers = _rulers(guests, start, end, home)
    if "co2" in rulers:
        planet = rulers["co2"][0]
        coming = [h for h in hours + astro.planetary_hours(hours[-1][1] + 60, lat, lon) if h[0] > end and h[2] == planet]
        act = "thin the crowd and let the purifier sing" if hazy(outdoor_pm25) else "air the room"
        prophecy["counsel"] = f"Your breath is heaviest in the hours of {_planet(planet)}; the next begins {_when(coming[0][0], end)}: {act} then."
    if rulers:
        ruled = sorted(rulers.items(), key=lambda r: -r[1][1])[:3]
        prophecy["revealed"] = _capital(_and([f"{_named(n)[1]} is ruled by {_planet(p)}, {PLANET_NATURES[p]} ({z:+.1f}σ in its hours)" for n, (p, z) in ruled])) + "."
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
        "rulers": {n: p for n, (p, _) in rulers.items()},
        "prophecy": prophecy,
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


def _region_lead(regions: dict[str, list], home: list) -> tuple[str, int, float, object] | None:
    """The region whose PM2.5 the haze at your door repeats best, one to three hours later:
    ``(region, lag in hours, r, a function foretelling your door's haze at a time)``."""
    stamps = sorted({round(t) for points in (*regions.values(), home) for t, _ in points})
    if len(stamps) < MIN_CELLS:
        return None
    hours = range(stamps[0], stamps[-1] + 1, 3600)
    at_home = {round(t): v for t, v in home}
    door = [at_home.get(h) for h in hours]
    best = None
    for region, points in regions.items():
        by_time = {round(t): v for t, v in points}
        cells = [by_time.get(h) for h in hours]
        for lag in range(1, 4):
            if (r := _paired_pearson(cells, door, lag)) is not None and abs(r) >= FRIENDS_AT and (best is None or abs(r) > abs(best[2])):
                best = (region, lag, r, cells)
    if best is None:
        return None
    region, lag, r, cells = best
    pairs = [(x, y) for x, y in zip(cells, door[lag:]) if x is not None and y is not None]
    slope, intercept = statistics.linear_regression([x for x, _ in pairs], [y for _, y in pairs])
    points = regions[region]
    own = [t for t, _ in points]

    def foretell(t):
        t -= lag * 3600
        return intercept + slope * _interpolate(points, own, t) if own[0] <= t <= own[-1] else None

    return region, lag, r, foretell


def foresee_elements(points, ctx, now, times):
    """The qi flows across the island: the haze at your door does what another region's did one to three hours before."""
    regions = {r: p for r, p in (ctx.get("regions") or {}).items() if len(p) > 2 and p != points}  # not your door's own
    if not (lead := _region_lead(regions, points)):
        return None
    return [lead[3](t) for t in times]


def _sheng(regions: dict[str, list]) -> tuple[int, int, float] | None:
    """How often the generating cycle came true: the region the haziest one feeds thickened over the next two hours.
    ``(times it did, times it was put to the test, how often any region thickens so)``."""
    by_time = {r: {round(t): v for t, v in regions[r]} for r in lore.ELEMENTS}
    region_of = {element: r for r, (element, _, _) in lore.ELEMENTS.items()}
    hits = trials = rises = 0
    for t in sorted(set.intersection(*(set(b) for b in by_time.values()))):
        if not all(t + 7200 in b for b in by_time.values()):
            continue
        haziest = max(lore.ELEMENTS, key=lambda r: by_time[r][t])
        fed = region_of[lore.GENERATES[lore.ELEMENTS[haziest][0]]]
        trials += 1
        hits += by_time[fed][t + 7200] > by_time[fed][t]
        rises += sum(b[t + 7200] > b[t] for b in by_time.values())
    return (hits, trials, rises / (5 * trials)) if trials >= 6 else None


def elements(regions: dict[str, list], home_pm25: list | None = None) -> dict | None:
    """NEA's five regions as the five phases, weighed by their PM2.5, and which way the haze flows between them.
    ``home_pm25`` is the PM2.5 at your door, one of them, for what the others foretell of it."""
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
    prophecy = {
        "counsel": f"Go {weak} for the cleanest air: {lore.ELEMENTS[weak][0]} breathes {means[weak]:.0f} µg/m³ there, where {excess} weighs {means[strong]:.0f}.",
    }
    others = {r: p for r, p in regions.items() if p != home_pm25}  # your door does not foretell itself
    if home_pm25 and (lead := _region_lead(others, home_pm25)):
        region, lag, r, foretell = lead
        ahead = home_pm25[-1][0] + lag * 3600
        if (then := foretell(ahead)) is not None:
            prophecy["foretold"] = (
                f"What {lore.ELEMENTS[region][0]} ({region}) breathes now, your door breathes {lag} h later (r = {r:+.2f}): "
                f"{max(0.0, then):.0f} µg/m³ {_when(ahead, home_pm25[-1][0])}."
            )
    if "foretold" not in prophecy:
        fed = lore.GENERATES[excess]
        prophecy["foretold"] = f"{excess} feeds {fed}: by the generating cycle, {next(r for r, e in lore.ELEMENTS.items() if e[0] == fed)} thickens next."
    if test := _sheng(regions):
        hits, trials, chance = test
        prophecy["revealed"] = (
            f"The generating cycle has foretold which region thickens next {hits} times in {trials} ({hits / trials:.0%}), "
            f"where chance would manage {chance:.0%}: " + ("the phases are real." if hits / trials > chance + 0.1 else "the phases are patient.")
        )
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
        "prophecy": prophecy,
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
    prophecy = {}
    if prevailing is not None:
        name, image, glyph = sectors[prevailing]["trigram"]
        prophecy["revealed"] = f"{sectors[prevailing]['wind']} comes under {name} {glyph}, {image}: it brings {WIND_GIFTS[name]}."
    now_blowing = _blowing(direction, speeds)
    if carried:
        cleanest = min(carried, key=lambda i: sectors[i]["haze"])
        if now_blowing in carried:
            s = sectors[now_blowing]
            prophecy["foretold"] = f"While {s['wind']} blows from the {s['direction']}, the haze will settle toward {s['haze']:.0f} µg/m³" + (
                f"; should {sectors[cleanest]['wind']} come from the {sectors[cleanest]['direction']} instead, {sectors[cleanest]['haze']:.0f}."
                if cleanest != now_blowing else ", the cleanest any wind has brought."
            )
        clean = sectors[cleanest]
        if clean["haze"] >= AIRING_PM25:
            prophecy["counsel"] = "No wind has brought clean air in this window: keep the windows shut, whichever way it blows."
        else:
            prophecy["counsel"] = f"Air the room when the wind comes from the {clean['direction']} ({clean['wind']}, {clean['haze']:.0f} µg/m³)" + (
                f", and keep it shut under {sectors[haziest]['wind']}." if haziest != cleanest else "."
            )
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
        "prophecy": prophecy,
    }


def _sector(degrees: float) -> int:
    return int((degrees + 22.5) % 360 // 45)


def _blowing(direction, speeds: dict) -> int | None:
    """The sector the wind blows from now, or None if it is calm."""
    t, degrees = direction[-1]
    return None if (s := speeds.get(t)) is not None and s < CALM else _sector(degrees)


def _memory(points, fallback: float = 3 * 3600) -> float:
    """How long ``points`` take to forget themselves: the e-folding time of their hour-to-hour autocorrelation."""
    hourly = [v for _, v in _bucket_means(points, 3600)]
    r = _pearson(hourly[:-1], hourly[1:])
    return -3600 / math.log(r) if r is not None and 0 < r < 1 else fallback


def foresee_winds(points, ctx, now, times):
    """The haze settles toward what the wind now blowing has brought before, as fast as the haze forgets itself."""
    direction = ctx.get("wind_direction") or []
    if not direction or len(points) < 3:
        return None
    speeds = dict(ctx["guests"].get("outdoor_wind_speed") or [])
    own, brought = [t for t, _ in points], {}
    for t, degrees in direction:
        if own[0] <= t <= own[-1]:
            calm = (s := speeds.get(t)) is not None and s < CALM
            brought.setdefault(None if calm else _sector(degrees), []).append(_interpolate(points, own, t))
    if len(brought.get(blowing := _blowing(direction, speeds), ())) < 3:
        return None
    settle, here, memory = statistics.fmean(brought[blowing]), _latest(points), _memory(points)
    return [settle + (here - settle) * math.exp(-(t - now) / memory) for t in times]


def _fan_wards(hours: list[tuple[float, float, float]], fan) -> dict[int, float]:
    """The ward's strength at each fan speed it ran at for three hours or more."""
    times = [t for t, _ in fan]
    by_speed: dict[int, list[tuple[float, float]]] = {}
    for t, outside, inside in hours:
        if times and times[0] <= t <= times[-1]:
            by_speed.setdefault(round(_interpolate(fan, times, t)), []).append((outside, inside))
    return {
        speed: 1 - statistics.fmean(i for _, i in pairs) / outside
        for speed, pairs in by_speed.items()
        if len(pairs) >= 3 and (outside := statistics.fmean(o for o, _ in pairs))
    }


def ward(indoor, outdoor, placements=(), end: float | None = None, fan=None, outdoor_pm25: float | None = None) -> dict | None:
    """How much of the outdoor PM2.5 the purifier's room keeps out, hour by hour, and how late the rest arrives.
    ``fan`` is the purifier's fan speed, to find the speed it wards best at."""
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
    at_door = outdoor[-1][1]
    arrives = "within the hour" if not lag else f"in {lag} h"
    prophecy = {
        "foretold": f"The haze now at your door, {at_door:.0f} µg/m³, reaches the purifier {arrives} as about {max(0.0, 1 - strength) * at_door:.0f}.",
        "revealed": f"Of every hundred motes that knock, {round(100 * min(1.0, max(0.0, 1 - strength)))} come in"
        + (", and the house adds its own." if breaches else "; the house adds none of its own."),
    }
    wards = _fan_wards(hours, fan or [])
    if len(wards) >= 2:
        best, worst = max(wards, key=wards.get), min(wards, key=wards.get)
        prophecy["counsel"] = f"The ward holds best with the fan at {best}: {wards[best]:.0%} of the haze held back, " + (
            f"against {wards[worst]:.0%} at {worst}." if wards[worst] >= 0 else f"while at {worst} the house makes its own haze, and the fan rises to meet it."
        )
    else:
        prophecy["counsel"] = "To strengthen the ward, run the purifier higher and keep the windows shut while the haze is thick."
    if hazy(outdoor_pm25):
        prophecy["counsel"] += " The haze is thick now: keep the windows shut."
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
        "prophecy": prophecy,
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
            schumann(co2, outdoor_pm25),
            golden_ratio(co2, outdoor_pm25),
            numerology(co2),
            zodiac(co2, temperature, end),
            voices(signals or {}, co2, temperature, start, end),
        ]
    household = [
        iching(pool if recent is None else recent, end),
        society(guests, start, end, placements, home),
        choir(guests),
        souls(co2, placements, end, outdoor_pm25) if co2 else None,
        births(born or {}, end),
        clock(guests, start, end, home, outdoor_pm25),
        elements(regions or {}, others.get("outdoor_pm25")),
        winds(others.get("outdoor_wind_direction"), others.get("outdoor_wind_speed"), others.get("outdoor_rain"), others.get("outdoor_pm25")),
        ward(others.get("blueair_pm25"), others.get("outdoor_pm25"), placements, end, others.get("blueair_fan_speed"), outdoor_pm25),
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
