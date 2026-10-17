"""Just enough real lore to make the pseudo-science sound learned.

The tables below are as their traditions have them: the I Ching's King Wen
sequence with Richard Wilhelm's names for the hexagrams, the eight trigrams
and their compass points in the Later Heaven arrangement, the five phases,
the winds of the Tower of the Winds in Athens, the astrological houses, the
Chinese zodiac, Krumhansl and Kessler's key profiles from music
psychology, and the church modes with their ethos. Only their application to air is new.
"""

from __future__ import annotations

# Trigram -> (name, image, glyph); lines from the bottom, True for yang.
TRIGRAMS = {
    (True, True, True): ("Qian", "Heaven", "☰"),
    (True, True, False): ("Dui", "Lake", "☱"),
    (True, False, True): ("Li", "Fire", "☲"),
    (True, False, False): ("Zhen", "Thunder", "☳"),
    (False, True, True): ("Xun", "Wind", "☴"),
    (False, True, False): ("Kan", "Water", "☵"),
    (False, False, True): ("Gen", "Mountain", "☶"),
    (False, False, False): ("Kun", "Earth", "☷"),
}

# The King Wen number of the hexagram with the lower trigram (row) under the upper one (column).
_KING_WEN_ORDER = ("Qian", "Zhen", "Kan", "Gen", "Kun", "Xun", "Li", "Dui")
_KING_WEN = (
    (1, 34, 5, 26, 11, 9, 14, 43),
    (25, 51, 3, 27, 24, 42, 21, 17),
    (6, 40, 29, 4, 7, 59, 64, 47),
    (33, 62, 39, 52, 15, 53, 56, 31),
    (12, 16, 8, 23, 2, 20, 35, 45),
    (44, 32, 48, 18, 46, 57, 50, 28),
    (13, 55, 63, 22, 36, 37, 30, 49),
    (10, 54, 60, 41, 19, 61, 38, 58),
)

HEXAGRAMS = (  # Wilhelm's names, by King Wen number
    "The Creative", "The Receptive", "Difficulty at the Beginning", "Youthful Folly", "Waiting", "Conflict",
    "The Army", "Holding Together", "The Taming Power of the Small", "Treading", "Peace", "Standstill",
    "Fellowship with Men", "Possession in Great Measure", "Modesty", "Enthusiasm", "Following",
    "Work on What Has Been Spoiled", "Approach", "Contemplation", "Biting Through", "Grace", "Splitting Apart",
    "Return", "Innocence", "The Taming Power of the Great", "The Corners of the Mouth",
    "Preponderance of the Great", "The Abysmal", "The Clinging", "Influence", "Duration", "Retreat",
    "The Power of the Great", "Progress", "Darkening of the Light", "The Family", "Opposition", "Obstruction",
    "Deliverance", "Decrease", "Increase", "Break-through", "Coming to Meet", "Gathering Together",
    "Pushing Upward", "Oppression", "The Well", "Revolution", "The Caldron", "The Arousing", "Keeping Still",
    "Development", "The Marrying Maiden", "Abundance", "The Wanderer", "The Gentle", "The Joyous", "Dispersion",
    "Limitation", "Inner Truth", "Preponderance of the Small", "After Completion", "Before Completion",
)


def hexagram(lines: list[bool]) -> int:
    """King Wen number of six lines, from the bottom, True for yang."""
    lower, upper = TRIGRAMS[tuple(lines[:3])][0], TRIGRAMS[tuple(lines[3:])][0]
    return _KING_WEN[_KING_WEN_ORDER.index(lower)][_KING_WEN_ORDER.index(upper)]


# The eight winds, clockwise from north: (abbreviation, direction, Greek wind, trigram there in the
# Later Heaven arrangement).
WINDS = (
    ("N", "north", "Boreas", (False, True, False)),
    ("NE", "north-east", "Kaikias", (False, False, True)),
    ("E", "east", "Apeliotes", (True, False, False)),
    ("SE", "south-east", "Euros", (False, True, True)),
    ("S", "south", "Notos", (True, False, True)),
    ("SW", "south-west", "Lips", (False, False, False)),
    ("W", "west", "Zephyros", (True, True, False)),
    ("NW", "north-west", "Skiron", (True, True, True)),
)

# The five phases (wuxing) and the compass point each stands for: NEA's five regions.
ELEMENTS = {  # region -> (element, character, colour)
    "east": ("Wood", "木", "green"),
    "south": ("Fire", "火", "red"),
    "central": ("Earth", "土", "yellow"),
    "west": ("Metal", "金", "white"),
    "north": ("Water", "水", "black"),
}
GENERATES = {"Wood": "Fire", "Fire": "Earth", "Earth": "Metal", "Metal": "Water", "Water": "Wood"}
OVERCOMES = {"Wood": "Earth", "Earth": "Water", "Water": "Fire", "Fire": "Metal", "Metal": "Wood"}

# What each astrological house governs, from the first.
HOUSES = (
    "the self", "possessions", "communication", "home and family", "pleasure", "health and chores",
    "partnerships", "death and transformation", "travel and philosophy", "career and reputation",
    "friends and hopes", "secrets and solitude",
)


def house(solar_hour: float) -> int:
    """The house (1-12) the Sun occupies at this solar time, taking sunrise as 6:00.

    The Sun rises at the cusp of the 1st house and moves clockwise through
    the 12th, 11th and 10th to culminate at noon.
    """
    return int((6 - solar_hour) % 24 // 2) + 1


# The Chinese zodiac: a year's animal and element follow the sexagenary cycle, which began a round in 4 AD.
ANIMALS = ("Rat", "Ox", "Tiger", "Rabbit", "Dragon", "Snake", "Horse", "Goat", "Monkey", "Rooster", "Dog", "Pig")
STEM_ELEMENTS = ("Wood", "Fire", "Earth", "Metal", "Water")


def chinese_year(year: int) -> tuple[str, str]:
    """``(element, animal)`` of the Chinese year that begins in ``year``."""
    return STEM_ELEMENTS[(year - 4) % 10 // 2], ANIMALS[(year - 4) % 12]


NOTES = ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")
# Key names as musicians spell them, by tonic pitch class.
MAJOR_KEYS = ("C", "D♭", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B")
MINOR_KEYS = ("C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "G♯", "A", "B♭", "B")
# How well each pitch class above the tonic fits a key, as listeners rated it (Krumhansl & Kessler 1982).
MAJOR_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
MINOR_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)

# The seven diatonic modes, brightest first, as Persichetti ranked them (Twentieth-Century Harmony, 1961):
# each is the one before with one note lowered. Their names are Glarean's (Dodecachordon, 1547), borrowed
# from Greek modes that were other scales; the ethos is half the Greeks' and half the centuries since.
MODES = (
    ("Lydian", (0, 2, 4, 6, 7, 9, 11), "Its raised fourth floats: the sound of wonder, which Plato banished from his Republic as soft and fit for drinking parties."),
    ("Ionian", (0, 2, 4, 5, 7, 9, 11), "Our major scale, which older theorists called the modus lascivus, too cheerful for church."),
    ("Mixolydian", (0, 2, 4, 5, 7, 9, 10), "Major with a flattened seventh, a folk song's mode; Plato heard its Greek namesake as a dirge."),
    ("Dorian", (0, 2, 3, 5, 7, 9, 10), "Minor with a raised sixth that leaves a door ajar; Plato kept the Dorian for the brave."),
    ("Aeolian", (0, 2, 3, 5, 7, 8, 10), "The natural minor, which Glarean added in 1547: sorrow, but orderly."),
    ("Phrygian", (0, 1, 3, 5, 7, 8, 10), "Its second sits a half step above the tonic: the sigh of flamenco and of the Spanish lament."),
    ("Locrian", (0, 1, 3, 5, 6, 8, 10), "Its fifth is diminished, so its home chord will not stand. Glarean named it only to set it aside as unusable."),
)
# Tempo markings, by the beats a minute below which they apply on Maelzel's metronome (1815).
TEMPI = ((56, "Largo", "broadly"), (66, "Adagio", "at ease"), (78, "Andante", "at a walking pace"), (float("inf"), "Moderato", "moderately"))
