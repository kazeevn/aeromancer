"""Kabbalistic analysis of the timeseries, in the Oracle's tradition.

Every number is computed honestly from the data; every reading is not. The
Tree of Life, the 22 paths and their letters, the gematria values and the
sefirot of the days of the week follow the usual (Golden Dawn / Kircher and
mispar hechrachi) attributions; their bearing on your ventilation is nil.
Name-finding, Atbash and the coincidences borrow their methods from Scott
Alexander's novel Unsong (https://unsongbook.com/).
"""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from datetime import datetime
from typing import NamedTuple

from .oracle import _interpolate, _pick, airing

STEADY_PPM_PER_MIN = 0.5  # slower than this, the air is in balance
STUFFY_PPM = 1000
VESSEL_MENDING = 0.95  # a shattered vessel is mended only below this share of its limit


class Instrument(NamedTuple):
    label: str
    unit: str
    decimals: int

    def fmt(self, value: float) -> str:
        text = f"{value:.{self.decimals}f}"
        return f"{text} {self.unit}" if self.unit else text


# Everything recorded, under the names the analysis gets it by. NEA's are the home region's PM2.5 and the
# nearest weather station's; wind direction is left out, since an average of compass bearings means nothing,
# and so is the Blueair's CO2, which is an estimate from its VOC sensor (docs/archive/blueair-eco2.md).
INSTRUMENTS = {
    "co2": Instrument("zyTemp CO₂", "ppm", 0),
    "temperature": Instrument("zyTemp temperature", "°C", 1),
    "humidity": Instrument("zyTemp humidity", "%", 0),
    "blueair_pm1": Instrument("indoor PM1", "µg/m³", 0),
    "blueair_pm25": Instrument("indoor PM2.5", "µg/m³", 0),
    "blueair_pm10": Instrument("indoor PM10", "µg/m³", 0),
    "blueair_voc": Instrument("VOC", "ppb", 0),
    "blueair_all_pollution": Instrument("Blueair pollution index", "%", 0),
    "blueair_temperature": Instrument("Blueair temperature", "°C", 1),
    "blueair_humidity": Instrument("Blueair humidity", "%", 0),
    "blueair_fan_speed": Instrument("Blueair fan speed", "", 1),
    "blueair_auto_mode": Instrument("Blueair auto mode", "", 2),
    "outdoor_pm25": Instrument("outdoor PM2.5", "µg/m³", 0),
    "outdoor_temperature": Instrument("outdoor temperature", "°C", 1),
    "outdoor_humidity": Instrument("outdoor humidity", "%", 0),
    "outdoor_rain": Instrument("rain", "mm per 5 min", 1),
    "outdoor_wind_speed": Instrument("wind speed", "m/s", 1),
}

# The seven vessels, one per lower sefira, as in Luria's account of the seven that shattered:
# quantity, limit at which it breaks (WHO 2021 24-hour guidelines for particles; the choir's VOC comfort), sefira.
VESSELS = (
    ("co2", STUFFY_PPM, "Chesed"),
    ("blueair_voc", 300, "Gevurah"),
    ("blueair_pm25", 15, "Tiferet"),
    ("blueair_pm10", 45, "Netzach"),
    ("outdoor_pm25", 15, "Hod"),
    ("humidity", 70, "Yesod"),
    ("blueair_humidity", 70, "Malkhut"),
)

# Pillar of each trend: Severity on the left as the tree is drawn, Mercy on the right.
PILLARS = {"rising": "Severity", "steady": "Balance", "falling": "Mercy"}

# Name, Hebrew, meaning, trend (pillar), upper CO2 bound (ppm), position on the tree (x, y).
SEFIROT = (
    ("Keter", "כתר", "Crown", "steady", 500, (0, 0)),
    ("Chokhmah", "חכמה", "Wisdom", "falling", 600, (1, 1)),
    ("Binah", "בינה", "Understanding", "rising", 600, (-1, 1)),
    ("Chesed", "חסד", "Kindness", "falling", 1000, (1, 2.6)),
    ("Gevurah", "גבורה", "Severity", "rising", 1000, (-1, 2.6)),
    ("Tiferet", "תפארת", "Beauty", "steady", 800, (0, 3.6)),
    ("Netzach", "נצח", "Endurance", "falling", math.inf, (1, 4.6)),
    ("Hod", "הוד", "Splendour", "rising", math.inf, (-1, 4.6)),
    ("Yesod", "יסוד", "Foundation", "steady", 1200, (0, 5.6)),
    ("Malkhut", "מלכות", "Kingdom", "steady", math.inf, (0, 7)),
)
SEFIRA_READINGS = {  # Malkhut's {airing} is filled in from the outdoor air
    "Keter": "The Crown: air so thin and still it is barely there, like a thought not yet thought.",
    "Chokhmah": "Wisdom: the air is clearing, as if remembering something it was told long ago.",
    "Binah": "Understanding: the air gathers itself slowly, the way a secret does.",
    "Chesed": "Kindness: the room is quietly forgiven its exhalations.",
    "Gevurah": "Severity: judgement gathers in the corners, at roughly the rate of two people typing.",
    "Tiferet": "Beauty: the still point where the breath in and the breath out agree to a truce.",
    "Netzach": "Endurance: the air is heavy, but it has begun the long walk home.",
    "Hod": "Splendour, of a heavy and accumulating kind. Something in the room is being built from breath.",
    "Yesod": "The Foundation: thick, unmoving, and load-bearing. The room has settled into itself.",
    "Malkhut": "The Kingdom: the material world, where breath sinks and grows heavy. {airing}",
}

# The 22 paths: letter, its name, the two sefirot it joins.
PATHS = (
    ("א", "Aleph", "Keter", "Chokhmah"),
    ("ב", "Beth", "Keter", "Binah"),
    ("ג", "Gimel", "Keter", "Tiferet"),
    ("ד", "Daleth", "Chokhmah", "Binah"),
    ("ה", "Heh", "Chokhmah", "Tiferet"),
    ("ו", "Vav", "Chokhmah", "Chesed"),
    ("ז", "Zayin", "Binah", "Tiferet"),
    ("ח", "Cheth", "Binah", "Gevurah"),
    ("ט", "Teth", "Chesed", "Gevurah"),
    ("י", "Yod", "Chesed", "Tiferet"),
    ("כ", "Kaph", "Chesed", "Netzach"),
    ("ל", "Lamed", "Gevurah", "Tiferet"),
    ("מ", "Mem", "Gevurah", "Hod"),
    ("נ", "Nun", "Tiferet", "Netzach"),
    ("ס", "Samekh", "Tiferet", "Yesod"),
    ("ע", "Ayin", "Tiferet", "Hod"),
    ("פ", "Peh", "Netzach", "Hod"),
    ("צ", "Tzaddi", "Netzach", "Yesod"),
    ("ק", "Qoph", "Netzach", "Malkhut"),
    ("ר", "Resh", "Hod", "Yesod"),
    ("ש", "Shin", "Hod", "Malkhut"),
    ("ת", "Tav", "Yesod", "Malkhut"),
)

LETTER_VALUES = {
    **dict(zip("אבגדהוזחט", range(1, 10))),
    **dict(zip("יכלמנסעפצ", range(10, 100, 10))),
    **dict(zip("קרשת", range(100, 500, 100))),
    **dict(zip("ךםןףץ", (20, 40, 50, 80, 90))),  # final forms keep their letter's value
}
GERESH, GERSHAYIM = "׳", "״"

# Hebrew, transliteration, meaning. Values are computed, not trusted.
LEXICON = (
    ("פחמן דו חמצני", "pachman du-chamtzani", "carbon dioxide"),
    ("חשמל", "chashmal", "electricity; Ezekiel's glowing amber"),
    ("שכינה", "Shekhinah", "the indwelling presence"),
    ("נשימה", "neshimah", "a breath"),
    ("אור אין סוף", "Or Ein Sof", "the endless light"),
    ("נפש", "nefesh", "the animal soul"),
    ("דלת", "delet", "a door"),
    ("אמת", "emet", "truth"),
    ("מאוורר", "me'avrer", "a fan"),
    ("מטהר אוויר", "metaher avir", "an air purifier"),
    ("חדר סגור", "cheder sagur", "a closed room"),
    ("מלכות", "Malkhut", "the Kingdom"),
    ("רוח סערה", "ruach se'arah", "a stormwind"),
    ("תיקון", "tikkun", "repair"),
    ("חלון פתוח", "chalon patuach", "an open window"),
    ("תורה", "Torah", "the teaching"),
    ("כתר", "Keter", "the Crown"),
    ("קליפות", "kelipot", "the husks that hide the light"),
    ("רוח הקודש", "ruach ha-kodesh", "the holy spirit"),
    ("שמש", "shemesh", "the Sun"),
    ("שבת", "Shabbat", "the day of rest"),
    ("תיקון עולם", "tikkun olam", "the repair of the world"),
    ("תשובה", "teshuvah", "return"),
    ("ספירות", "sefirot", "the emanations"),
    ("נשמת חיים", "nishmat chayim", "the breath of life"),
    ("גלגול נשמות", "gilgul neshamot", "the wheel of souls"),
    ("בראשית", "Bereshit", "in the beginning"),
    ("שבירת הכלים", "shevirat ha-kelim", "the breaking of the vessels"),
    ("ספירת העומר", "sefirat ha-omer", "the counting of the Omer"),
    ("תפארת", "Tiferet", "Beauty"),
    ("תחיית המתים", "techiyat ha-metim", "the revival of the dead"),
    ("מעשה בראשית", "ma'aseh bereshit", "the work of creation"),
    ("תקיעת שופר", "teki'at shofar", "a blast of the shofar"),
)

# Short words the Llull listens for in the air's chant, as in Unsong's Name-finding.
NAMES = (
    ("אויר", "avir", "air"),
    ("חלון", "chalon", "window"),
    ("רוח", "ruach", "wind, spirit"),
    ("הבל", "hevel", "vapour"),
    ("אור", "or", "light"),
    ("אמת", "emet", "truth"),
    ("אמן", "amen", "amen"),
    ("נפש", "nefesh", "soul"),
    ("אדם", "adam", "human"),
    ("עפר", "afar", "dust"),
    ("מים", "mayim", "water"),
    ("שמש", "shemesh", "sun"),
    ("ירח", "yareach", "moon"),
    ("חי", "chai", "alive"),
    ("אש", "esh", "fire"),
    ("אף", "af", "nose"),
    ("לב", "lev", "heart"),
    ("שם", "shem", "name"),
    ("עץ", "etz", "tree"),
    ("גן", "gan", "garden"),
)
WORDS = LEXICON + NAMES

ALEPHBET = "אבגדהוזחטיכלמנסעפצקרשת"
FINALS = str.maketrans("ךםןףץ", "כמנפצ")
ATBASH = str.maketrans(ALEPHBET, ALEPHBET[::-1])

# (number, what it is), for the coincidences.
SACRED = (
    (7, "the days of creation"),
    (10, "the number of sefirot"),
    (13, "the attributes of mercy"),
    (18, "chai, life"),
    (22, "the letters of the alphabet"),
    (26, "the value of the Tetragrammaton"),
    (32, "the paths of wisdom"),
    (36, "the hidden righteous"),
    (42, "the length of the 42-letter Name"),
    (50, "the gates of understanding"),
    (72, "the Names of the Shem HaMephorash"),
    (137, "the value of קבלה, Kabbalah"),
    (216, "the letters of the 72-fold Name"),
    (248, "the positive commandments"),
    (365, "the negative commandments"),
    (613, "the commandments"),
)
COINCIDENCE_WAYS = ("exact", "mirror", "hidden", "digits", "multiple")

# Sunday to Saturday, as in the counting of the Omer.
WEEKDAY_SEFIROT = ("Chesed", "Gevurah", "Tiferet", "Netzach", "Hod", "Yesod", "Malkhut")
DAY_NAMES = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Shabbat")

CERTAINTIES = (
    "as above, so below",
    "attested by gematria",
    "hidden in the Zohar, probably",
    "revealed to a USB device",
    "written in the white spaces between the letters",
    "one of the 72 names agrees",
    "nothing is a coincidence",
    "registered with UNSONG",
)


def _times(n: int) -> str:
    return {1: "once", 2: "twice"}.get(n, f"{n} times")


def gematria(text: str) -> int:
    """Standard (mispar hechrachi) value; anything but Hebrew letters counts as nothing."""
    return sum(LETTER_VALUES.get(c, 0) for c in text)


def _letters(n: int) -> str:
    """Letters for 1 <= n <= 999, without punctuation."""
    hundreds, rest = divmod(n, 100)
    out = "ת" * (hundreds // 4) + ("", "ק", "ר", "ש")[hundreds % 4]
    if rest in (15, 16):  # spelled 9+6 and 9+7 so as not to write a divine name
        return out + ("טו" if rest == 15 else "טז")
    tens, units = divmod(rest, 10)
    return out + ("" if not tens else "יכלמנסעפצ"[tens - 1]) + ("" if not units else "אבגדהוזחט"[units - 1])


def hebrew_numeral(n: int) -> str:
    """1..999999 as Hebrew numerals: 734 -> תשל״ד, 1200 -> א׳ר׳, 5786 -> ה׳תשפ״ו."""
    if not 1 <= n <= 999_999:
        raise ValueError(f"no Hebrew numeral for {n}")
    thousands, rest = divmod(n, 1000)
    out = _letters(thousands) + GERESH if thousands else ""
    if rest:
        tail = _letters(rest)
        out += tail + GERESH if len(tail) == 1 else tail[:-1] + GERSHAYIM + tail[-1]
    return out


def _smoothed(co2):
    w = max(1, len(co2) // 50)
    return [statistics.fmean(v for _, v in co2[max(0, i - w) : i + w + 1]) for i in range(len(co2))]


def _trends(co2) -> list[str]:
    """Rising, steady or falling at each reading, from the smoothed slope into it."""
    smooth = _smoothed(co2)
    out = ["steady"]
    for i in range(1, len(co2)):
        dt = co2[i][0] - co2[i - 1][0]
        rate = (smooth[i] - smooth[i - 1]) / dt * 60 if dt > 0 else 0.0
        out.append("steady" if abs(rate) < STEADY_PPM_PER_MIN else "rising" if rate > 0 else "falling")
    return out


def sefira_of(ppm: float, trend: str) -> str:
    return next(s[0] for s in SEFIROT if s[3] == trend and ppm < s[4])


def _aligned(points, times: list[float]) -> list[float | None]:
    """``points`` at each of ``times``, interpolated; None outside their span."""
    if len(points) < 2:
        return [None] * len(times)
    own = [t for t, _ in points]
    return [_interpolate(points, own, t) if own[0] <= t <= own[-1] else None for t in times]


def _sefira_means(sefirot: list[str], others: dict) -> tuple[dict, str]:
    """Each other instrument's mean while the air was in each sefira, and a sentence on the one that moves most."""
    by_sefira = {s[0]: {} for s in SEFIROT}
    best = None
    for key, values in others.items():
        groups = {}
        for s, v in zip(sefirot, values):
            if v is not None:
                groups.setdefault(s, []).append(v)
        for s, vs in groups.items():
            by_sefira[s][key] = statistics.fmean(vs)
        everything = [v for vs in groups.values() for v in vs]
        settled = {s: statistics.fmean(vs) for s, vs in groups.items() if len(vs) >= max(3, len(sefirot) // 20)}
        if len(settled) < 2 or len(everything) < 2 or not (spread := statistics.pstdev(everything)):
            continue
        lo, hi = min(settled, key=settled.get), max(settled, key=settled.get)
        moved = (settled[hi] - settled[lo]) / spread
        if best is None or moved > best[0]:
            best = (moved, key, lo, settled[lo], hi, settled[hi])
    if best is None:
        return by_sefira, ""
    _, key, lo, lo_v, hi, hi_v = best
    inst = INSTRUMENTS[key]
    return by_sefira, (
        f" Of the other instruments, the {inst.label} walks closest in its footsteps: "
        f"{inst.fmt(lo_v)} in {lo}, {inst.fmt(hi_v)} in {hi}."
    )


def tree_of_life(co2, others: dict | None = None, outdoor_pm25: float | None = None):
    """``others`` maps instrument keys to their points, to be read at each sefira the CO2 visits."""
    sefirot = [sefira_of(v, trend) for (_, v), trend in zip(co2, _trends(co2))]
    times = [t for t, _ in co2]
    means, follows = _sefira_means(sefirot, {k: _aligned(p, times) for k, p in (others or {}).items()})
    counts = {s[0]: 0 for s in SEFIROT}
    for s in sefirot:
        counts[s] += 1
    paths = {frozenset((a, b)): 0 for _, _, a, b in PATHS}
    leaps = 0
    for a, b in zip(sefirot, sefirot[1:]):
        if a == b:
            continue
        if frozenset((a, b)) in paths:
            paths[frozenset((a, b))] += 1
        else:
            leaps += 1
    total = len(sefirot)
    dominant = max(counts, key=counts.get)
    trodden = sum(paths.values())
    lower, floor = {}, dict.fromkeys(PILLARS, None)  # each band starts where the one above it in its pillar ends
    for name, _, _, trend, upper, _ in SEFIROT:
        lower[name], floor[trend] = floor[trend], upper
    entries = [
        {
            "name": name,
            "hebrew": hebrew,
            "meaning": meaning,
            "pillar": PILLARS[trend],
            "trend": trend,
            "lower": lower[name],
            "upper": None if math.isinf(upper) else upper,
            "x": x,
            "y": y,
            "share": counts[name] / total,
            "means": means[name],
        }
        for name, hebrew, meaning, trend, upper, (x, y) in SEFIROT
    ]
    path_entries = [
        {"letter": letter, "name": name, "a": a, "b": b, "count": paths[frozenset((a, b))]} for letter, name, a, b in PATHS
    ]
    if trodden:
        best = max(path_entries, key=lambda p: p["count"])
        walk = (
            f"It moved {_times(trodden + leaps)} between the sefirot; {trodden} of those steps kept to the 22 paths, "
            f"and the most worn of them is {best['name']} ({best['letter']}), from {best['a']} to {best['b']}, "
            f"trodden {_times(best['count'])}."
        )
    else:
        walk = "It has not yet set foot on any of the 22 paths."
    if leaps:
        walk += f" {_times(leaps).capitalize()} it leapt across the Abyss, where no path runs and no one should walk."
    return {
        "id": "tree",
        "title": "Tree of Life",
        "headline": f"{dominant} ({next(e['hebrew'] for e in entries if e['name'] == dominant)})",
        "body": f"For {counts[dominant] / total:.0%} of its hours, your air dwelt in {dominant}. "
        f"{SEFIRA_READINGS[dominant].format(airing=airing(outdoor_pm25))} {walk}{follows}",
        "sefirot": entries,
        "paths": path_entries,
        "leaps": leaps,
    }


def _nearest_word(n: int, words=LEXICON):
    return min(words, key=lambda w: (abs(gematria(w[0]) - n), gematria(w[0])))


def gematria_reading(co2, means: dict | None = None):
    """``means`` maps every instrument with readings, the CO2 one included, to its mean."""
    mean = round(statistics.fmean(v for _, v in co2))
    now = round(co2[-1][1])
    word, translit, meaning = _nearest_word(mean)
    value = gematria(word)
    gap = mean - value
    if gap == 0:
        relation = f"It is, to the letter, {word} ({translit}, {meaning}). Some numbers are not chosen; they are found."
    else:
        relation = (
            f"It stands {abs(gap)} {'past' if gap > 0 else 'short of'} {word} ({translit}, {meaning}), "
            f"which counts {value}."
        )
    now_word, now_translit, _ = _nearest_word(now)
    total = sum(round(m) for m in (means or {}).values())
    whole = ""
    if len(means or {}) > 1:
        total_word, total_translit, total_meaning = _nearest_word(total, WORDS)
        whole = (
            f" Sum the means of all {len(means)} instruments, heedless of their units, and the room's true name "
            f"surfaces: {total}, nearest {total_word} ({total_translit}, {total_meaning})."
        )
    return {
        "id": "gematria",
        "title": "Gematria",
        "headline": hebrew_numeral(mean),
        "body": f"Your mean, {mean} ppm, is written {hebrew_numeral(mean)}. {relation} "
        f"The newest breath, {now} ppm, leans toward {now_word} ({now_translit}).{whole}",
        "mean": mean,
        "word": word,
        "translit": translit,
        "meaning": meaning,
        "value": value,
        "total": total,
    }


def _weekday(t: float) -> int:
    return (datetime.fromtimestamp(t).weekday() + 1) % 7  # Sunday first


def _day_means(points) -> list[float | None]:
    days = [[] for _ in range(7)]
    for t, v in points:
        days[_weekday(t)].append(v)
    return [statistics.fmean(d) if d else None for d in days]


def _shabbat_rest(series: dict) -> str:
    """Which instruments read lower on Shabbat than on the other days, on average, as a sentence."""
    resting, judged = [], 0
    for key, points in series.items():
        means = _day_means(points)
        others = [m for m in means[:6] if m is not None]
        if means[6] is None or not others:
            continue
        judged += 1
        if means[6] < statistics.fmean(others):
            resting.append(INSTRUMENTS[key].label)
    if judged < 2:
        return ""
    named = f": {', '.join(resting)}" if 0 < len(resting) <= 4 else ""
    return f" On Shabbat, {len(resting)} of {judged} instruments fall quiet, reading lower than on the other days{named}."


def week_of_creation(co2, end, series: dict | None = None):
    """``series`` maps every instrument with readings to its points, for the Shabbat rest."""
    means = _day_means(co2)
    today = _weekday(end)
    seen = [i for i, m in enumerate(means) if m is not None]
    if len(seen) < 2:
        body = (
            f"Today is {DAY_NAMES[today]}, and {WEEKDAY_SEFIROT[today]} keeps watch over it. "
            "One day reveals nothing of the week; widen the range, and the pattern may show itself."
        )
    else:
        best, worst = min(seen, key=means.__getitem__), max(seen, key=means.__getitem__)
        body = (
            f"Your air is lightest on {DAY_NAMES[best]} ({WEEKDAY_SEFIROT[best]}, {means[best]:.0f} ppm) "
            f"and heaviest on {DAY_NAMES[worst]} ({WEEKDAY_SEFIROT[worst]}, {means[worst]:.0f} ppm). "
        )
        if worst == 6:
            body += "Shabbat is a day of rest, and the air rests heavily upon it."
        elif best == 6:
            body += "On Shabbat the room exhales, as if it had waited all week to."
        else:
            body += "Shabbat is neither its best day nor its worst, which is its own kind of rest."
        body += _shabbat_rest(series or {})
    return {
        "id": "week",
        "title": "Week of creation",
        "headline": f"{DAY_NAMES[today]}, day of {WEEKDAY_SEFIROT[today]}",
        "body": body,
        "days": [
            {"day": d, "sefira": s, "mean": m, "today": i == today}
            for i, (d, s, m) in enumerate(zip(DAY_NAMES, WEEKDAY_SEFIROT, means))
        ],
    }


def vessel(points, limit: float) -> dict:
    """How often ``points`` reached ``limit`` (shattered) and fell back below VESSEL_MENDING of it (mended)."""
    shattered = mended = 0
    broken = False
    broken_since = None
    exile = longest = 0.0
    for i, (t, v) in enumerate(points):
        if i and broken:
            exile += t - points[i - 1][0]
        if not broken and v >= limit:
            broken, broken_since = True, t
            shattered += 1
        elif broken and v < limit * VESSEL_MENDING:
            broken = False
            mended += 1
            longest = max(longest, t - broken_since)
    if broken:
        longest = max(longest, points[-1][0] - broken_since)
    span = points[-1][0] - points[0][0]
    return {
        "shattered": shattered,
        "mended": mended,
        "broken": broken,
        "exile_share": exile / span if span else 0.0,
        "longest": longest,
    }


def vessels(series: dict):
    """Each of the seven vessels whose instrument has readings."""
    rows = [
        {"key": key, "label": INSTRUMENTS[key].label, "sefira": sefira, "limit": limit,
         "unit": INSTRUMENTS[key].unit, **vessel(series[key], limit)}
        for key, limit, sefira in VESSELS
        if series.get(key)
    ]
    shattered = sum(r["shattered"] for r in rows)
    mended = sum(r["mended"] for r in rows)
    if not shattered:
        which = f"none of the {len(rows)} instruments" if len(rows) > 1 else f"the {rows[0]['label']} never"
        body = f"No vessel has shattered: {which} reached its limit. The light is still held, for now."
    else:
        worst = max(rows, key=lambda r: r["exile_share"])
        broken = [r["label"] for r in rows if r["broken"]]
        body = (
            f"The vessels shattered {_times(shattered)} and were mended "
            + (_times(mended) if mended else "never")
            + f". Longest in exile was the vessel of {worst['sefira']}, the {worst['label']} at {worst['limit']:g} "
            f"{worst['unit']}: broken {worst['exile_share']:.0%} of the time, and at its longest "
            f"{worst['longest'] / 3600:.1f} h without rest. "
            + (
                f"Still in pieces: {', '.join(broken)}. The sparks wait to be gathered."
                if broken
                else "Every vessel is whole again, for now."
            )
        )
    return {
        "id": "vessels",
        "title": "Breaking of the vessels",
        "headline": f"{shattered} shattered, {mended} mended",
        "body": body,
        "vessels": rows,
        "shattered": shattered,
        "mended": mended,
    }


def chant(points) -> str:
    """An instrument spelled one letter per reading: its value modulo 22, from א to ת."""
    return "".join(ALEPHBET[round(v) % len(ALEPHBET)] for _, v in points)


def _listen(stream: str):
    """Each Name's positions in ``stream``, and how many hits the same letters would give in random order."""
    frequency = {c: n / len(stream) for c, n in Counter(stream).items()}
    hits, expected = {}, 0.0
    for word, _, _ in NAMES:
        key = word.translate(FINALS)
        expected += max(0, len(stream) - len(key) + 1) * math.prod(frequency.get(c, 0.0) for c in key)
        if at := [m.start() for m in re.finditer(f"(?={key})", stream)]:  # overlapping, as a chant would
            hits[word] = at
    return hits, expected


def llull(series: dict):
    """Unsong's Name-finding: chant every syllable and listen for words, like a sweatshop or the Llull program.

    Each instrument chants on its own, and is judged against its own letters shuffled: a smooth series
    says fewer words than its letters would in random order, since it rarely jumps between them.
    """
    voices, heard = [], {}  # heard: word -> [(ts, instrument, stream, position)]
    for key, points in series.items():
        if len(points) < 2:
            continue
        stream = chant(points)
        hits, expected = _listen(stream)
        voices.append({"label": INSTRUMENTS[key].label, "letters": len(stream),
                       "found": sum(map(len, hits.values())), "expected": expected})
        for word, at in hits.items():
            heard.setdefault(word, []).extend((points[i][0], key, stream, i) for i in at)
    voices.sort(key=lambda v: v["expected"] - v["found"])
    found = sum(v["found"] for v in voices)
    expected = sum(v["expected"] for v in voices)
    names = sorted(
        ({"word": w, "translit": t, "meaning": m, "count": len(heard[w]), "first": min(heard[w])[0]}
         for w, t, m in NAMES if w in heard),
        key=lambda n: (-len(n["word"]), -n["count"]),
    )
    intro = (
        f"The Llull taught each of your {len(voices)} instruments to chant, one letter per reading (its value modulo "
        f"22): {sum(v['letters'] for v in voices)} letters in all, sung into the dark while it listened for "
        f"{len(NAMES)} words."
    )
    excerpt, cut, mark = "", [False, False], None
    if names:
        best = names[0]
        ts, key, stream, at = min(heard[best["word"]])
        k = len(best["word"])
        lo, hi = max(0, at - 8), at + k + 8
        excerpt, cut, mark = stream[lo:hi], [lo > 0, hi < len(stream)], [at - lo, at - lo + k]
        when = datetime.fromtimestamp(ts).strftime("%b %-d, %H:%M")
        if found > 1.5 * expected:
            verdict = "The air is trying to tell you something. UNSONG has been notified."
        elif found < expected / 1.5:
            verdict = "The air is keeping its Names to itself, as Names are wont to do."
        else:
            verdict = "Exactly as many as chance allows, which is what a careful Name would want you to think."
        eloquent = voices[0]
        body = (
            f"{intro} First it caught {best['word']} ({best['translit']}, {best['meaning']}), whispered by the "
            f"{INSTRUMENTS[key].label} on {when}; {found} word{'s' if found != 1 else ''} in all, where the same "
            f"letters shuffled would give about {expected:.1f}. {verdict} The most eloquent voice: "
            f"the {eloquent['label']}, {eloquent['found']} against {eloquent['expected']:.1f} shuffled."
        )
    else:
        body = (
            f"{intro} It heard only silence, where the same letters shuffled would give about {expected:.1f}. "
            "UNSONG has nothing to confiscate."
        )
    return {
        "id": "llull",
        "title": "Name-finding",
        "headline": f"{len(names)} Name{'s' if len(names) != 1 else ''} heard",
        "body": body,
        "letters": sum(v["letters"] for v in voices),
        "expected": expected,
        "excerpt": excerpt,
        "excerpt_cut": cut,  # whether the chant goes on before and after it
        "mark": mark,
        "names": names,
        "voices": voices,
    }


def _atbash(n: int) -> tuple[str, str, int]:
    """``n`` as unpunctuated numeral letters, their Atbash mirror, and the mirror's value."""
    plain = hebrew_numeral(n).replace(GERESH, "").replace(GERSHAYIM, "")
    mirror = plain.translate(ATBASH)
    return plain, mirror, gematria(mirror)


def _mirror_pair(means: dict) -> str:
    """The instrument whose mean, mirrored, comes closest to another instrument's mean, as a sentence."""
    best = None
    for a, mean_a in means.items():
        if round(mean_a) < 1:
            continue
        _, mirror, value = _atbash(round(mean_a))
        for b, mean_b in means.items():
            if b != a and mean_b > 0 and (best is None or abs(value - mean_b) / mean_b < best[0]):
                best = (abs(value - mean_b) / mean_b, a, mirror, value, b, mean_b)
    if best is None:
        return ""
    off, a, mirror, value, b, mean_b = best
    closeness = "falls exactly on" if round(off * 100) == 0 else f"falls within {off:.0%} of"
    return (
        f" Your instruments hold reflections of one another, too: the mean {INSTRUMENTS[a].label}, {round(means[a])}, "
        f"folds into {mirror}, {value}, which {closeness} the mean {INSTRUMENTS[b].label}, {INSTRUMENTS[b].fmt(mean_b)}."
    )


def temurah(co2, means: dict | None = None):
    """Atbash, the letter substitution Unsong's kabbalists (and Jeremiah) used, applied to the means."""
    mean = round(statistics.fmean(v for _, v in co2))
    numeral = hebrew_numeral(mean)
    plain, mirror, value = _atbash(mean)
    word, translit, meaning = _nearest_word(value, WORDS)
    gap = value - gematria(word)
    if gap == 0:
        relation = f"the very number of {word} ({translit}, {meaning})."
    else:
        relation = f"{abs(gap)} {'beyond' if gap > 0 else 'shy of'} {word} ({translit}, {meaning})."
    return {
        "id": "temurah",
        "title": "Atbash",
        "headline": mirror,
        "body": f"Atbash folds the alphabet back on itself, א onto ת and ב onto ש; it is how Jeremiah hid בבל inside "
        f"ששך. Folded so, your mean {numeral} becomes {mirror}, which counts {value}: {relation}"
        f"{_mirror_pair(means or {})}",
        "plain": plain,
        "mirror": mirror,
        "value": value,
        "word": word,
    }


def _coincides(n: int, s: int, way: str) -> bool:
    if way == "exact":
        return n == s
    if n == s:
        return False
    if way == "mirror":
        return s >= 10 and str(n)[::-1] == str(s)
    if way == "hidden":
        return s >= 10 and str(s) in str(n)
    if way == "digits":
        return sum(map(int, str(n))) == s
    return s >= 7 and n % s == 0  # multiple


def _say(label: str, n: int, s: int, what: str, way: str) -> str:
    cap = label[0].upper() + label[1:]
    return {
        "exact": f"{cap} is {n}: {what}.",
        "mirror": f"{cap} is {n}, which is {s} in a mirror: {what}.",
        "hidden": f"{cap}, {n}, hides {s}: {what}.",
        "digits": f"The digits of {label} ({n}) add up to {s}: {what}.",
        "multiple": f"{cap} is {n}, {n // s} × {s}: {what}, {n // s} times over.",
    }[way]


def coincidences(co2, others: dict | None = None):
    """Aaron Smith-Teller's method: take every number in sight and find what it secretly is.

    ``others`` maps the other instruments' keys to their points; their peaks and means join the CO2's numbers.
    """
    values = [v for _, v in co2]
    peak = max(range(len(values)), key=values.__getitem__)
    above = sum(b[0] - a[0] for a, b in zip(co2, co2[1:]) if a[1] >= STUFFY_PPM)
    facts = [
        ("your CO₂ peak", round(values[peak])),
        ("your CO₂ trough", round(min(values))),
        ("your mean CO₂", round(statistics.fmean(values))),
        ("your CO₂ swing", round(values[peak]) - round(min(values))),
        ("the latest CO₂ reading", round(values[-1])),
        ("the hour of your CO₂ peak", datetime.fromtimestamp(co2[peak][0]).hour),
        (f"your minutes at {STUFFY_PPM} ppm or more", round(above / 60)),
    ]
    for key, points in (others or {}).items():
        label = INSTRUMENTS[key].label
        facts += [
            (f"the {label} peak", round(max(v for _, v in points))),
            (f"the mean {label}", round(statistics.fmean(v for _, v in points))),
        ]
    facts = [(label, n) for label, n in facts if n >= 1]
    numbers = dict(SACRED)
    for word, _, meaning in WORDS:
        numbers.setdefault(gematria(word), f"the value of {word}, {meaning}")
    matches = sorted(
        (rank, -s, label, n, s, way)
        for label, n in facts
        for s in numbers
        for rank, way in enumerate(COINCIDENCE_WAYS)
        if _coincides(n, s, way)
    )
    comparisons = len(facts) * len(numbers) * len(COINCIDENCE_WAYS)
    shown, seen = [], set()  # the best three, each a different number found in a different fact
    for _, _, label, n, s, way in matches:
        if label not in seen and s not in seen and len(shown) < 3:
            seen |= {label, s}
            shown.append({"fact": label, "value": n, "sacred": s, "way": way, "text": _say(label, n, s, numbers[s], way)})
    if shown:
        body = (
            f"Your numbers had {comparisons} chances to be sacred, and took {len(matches)} of them. "
            "Nothing is a coincidence."
        )
    else:
        body = (
            f"Your numbers had {comparisons} chances to be sacred, and took none. This, too, is not a coincidence."
        )
    return {
        "id": "coincidences",
        "title": "Nothing is a coincidence",
        "headline": f"{len(matches)} coincidence{'s' if len(matches) != 1 else ''}",
        "body": body,
        "coincidences": shown,
        "comparisons": comparisons,
        "matches": len(matches),
    }


def analyze(series: dict[str, list[tuple[float, float]]], end: float, outdoor_pm25: float | None = None) -> dict:
    """``series`` maps INSTRUMENTS keys to ``(ts, value)`` lists in time order; any may be missing or empty.

    The tree walks on the zyTemp's CO2. ``outdoor_pm25`` is the latest outdoor PM2.5, if known, so the advice
    does not open windows into haze.
    """
    present = {key: series[key] for key in INSTRUMENTS if series.get(key)}
    if "co2" not in present:
        return {"findings": [], "instruments": [], "disclaimer": "The Tree needs CO2 readings to bear fruit."}
    co2 = present["co2"]
    others = {key: points for key, points in present.items() if key != "co2"}
    means = {key: statistics.fmean(v for _, v in points) for key, points in present.items()}
    findings = [
        tree_of_life(co2, others, outdoor_pm25),
        gematria_reading(co2, means),
        temurah(co2, means),
        week_of_creation(co2, end, present),
        vessels(present),
        llull(present),
        coincidences(co2, others),
    ]
    for f in findings:
        f["certainty"] = _pick(CERTAINTIES, f["id"], f["headline"])
    return {
        "findings": findings,
        "instruments": [{"key": key, **INSTRUMENTS[key]._asdict()} for key in present],
        "disclaimer": "Strictly pseudo-mystical. The arithmetic is real; the emanations are not.",
    }
