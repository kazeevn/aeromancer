"""The council of seers: every method that can foresee, asked together and weighed by how well it foresaw.

Each method of the Oracle and the Tree of Life that can say what a series will do next is a seer
(``foresee_<id>`` in oracle.py and kabbalah.py). The council asks every seer twice: once as if it were a
horizon ago, with only the readings it would have had then (the hindcast), and once now. Each hindcast is
scored against what the air then did, and against the Skeptic, who says nothing will change. The seers then
speak together, each weighed inversely to its hindcast's mean squared error, as Bates and Granger (1969)
combined forecasts, and the unified prophecy is read from what they say. The arithmetic is real; the
emanations are not.
"""

from __future__ import annotations

import math
import statistics

from . import kabbalah, oracle
from .oracle import _duration, _when

CELLS = 24  # a prophecy is told at the middles of this many cells
HORIZON_SHARE = 1 / 6  # the council looks ahead a sixth of what it has seen,
HORIZON = (600.0, 86400.0)  # but no less than ten minutes and no more than a day
EXACT = 1e-6  # added to every seer's squared error, so that a perfect one does not silence the rest by division

BREATH, HAZE = "co2", "outdoor_pm25"
TARGETS = {  # what the council foresees: name, unit, and the range no prophecy may leave
    BREATH: ("your breath", "ppm", (oracle.OUTDOOR_CO2 - 25, oracle.MAX_CO2)),
    HAZE: ("the haze at your door", "µg/m³", (0.0, 1000.0)),
}
# The seers: (id, name, tradition, how it foresees, what it foresees).
SEERS = (
    ("aura", "Aura", "Oracle", oracle.foresee_aura, (BREATH, HAZE)),
    ("moon", "Lunar influence", "Oracle", oracle.foresee_moon, (BREATH, HAZE)),
    ("mercury", "Mercury", "Oracle", oracle.foresee_mercury, (BREATH, HAZE)),
    ("chakra", "Chakra residency", "Oracle", oracle.foresee_chakra, (BREATH,)),
    ("schumann", "Schumann alignment", "Oracle", oracle.foresee_schumann, (BREATH, HAZE)),
    ("golden", "Divine proportion", "Oracle", oracle.foresee_golden, (BREATH, HAZE)),
    ("iching", "The I Ching", "Oracle", oracle.foresee_iching, (BREATH, HAZE)),
    ("society", "The sensor society", "Oracle", oracle.foresee_society, (BREATH, HAZE)),
    ("choir", "The household choir", "Oracle", oracle.foresee_choir, (BREATH, HAZE)),
    ("souls", "Souls present", "Oracle", oracle.foresee_souls, (BREATH,)),
    ("clock", "The celestial clock", "Oracle", oracle.foresee_clock, (BREATH, HAZE)),
    ("elements", "Five elements of the island", "Oracle", oracle.foresee_elements, (HAZE,)),
    ("winds", "The winds", "Oracle", oracle.foresee_winds, (HAZE,)),
    ("tree", "Tree of Life", "Tree of Life", kabbalah.foresee_tree, (BREATH,)),
    ("gematria", "Gematria", "Tree of Life", kabbalah.foresee_gematria, (BREATH, HAZE)),
    ("temurah", "Atbash", "Tree of Life", kabbalah.foresee_temurah, (BREATH, HAZE)),
    ("week", "Week of creation", "Tree of Life", kabbalah.foresee_week, (BREATH, HAZE)),
)
CHART_POINTS = 240  # of what actually happened, for the dashboard

# The Major Arcana the spread is dealt from: number, name, and the divinatory meaning Waite gives it, in a few of
# his words (The Pictorial Key to the Tarot, 1910, Part III).
ARCANA = {
    "lovers": (6, "The Lovers", "attraction, love, trials overcome"),
    "chariot": (7, "The Chariot", "providence, triumph, trouble"),
    "strength": (8, "Strength", "power, energy, courage"),
    "hermit": (9, "The Hermit", "prudence, circumspection"),
    "wheel": (10, "Wheel of Fortune", "destiny, fortune, success"),
    "hanged": (12, "The Hanged Man", "trials, sacrifice, divination, prophecy"),
    "temperance": (14, "Temperance", "economy, moderation"),
    "devil": (15, "The Devil", "violence, force, fatality"),
    "tower": (16, "The Tower", "unforeseen catastrophe"),
    "star": (17, "The Star", "hope and bright prospects"),
    "moon": (18, "The Moon", "hidden enemies, deception, occult forces"),
    "sun": (19, "The Sun", "material happiness, contentment"),
}
ROMAN = ("0", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI")
CERTAINTIES = (
    "weighed, found wanting, weighed again",
    "Bates and Granger, 1969",
    "inversely proportional to its doubts",
    "seventeen seers cannot all be wrong",
    "skill score positive, probably",
    "the Skeptic dissents",
)


def _then(ctx: dict, t: float) -> dict:
    """The context as it stood at ``t``: every series cut there."""
    guests = {name: cut for name, points in ctx["guests"].items() if len(cut := oracle._until(points, t)) >= 2}
    return {
        **ctx,
        "guests": guests,
        "regions": {r: oracle._until(points, t) for r, points in ctx["regions"].items()},
        "wind_direction": oracle._until(ctx["wind_direction"], t),
    }


def _ask(foresee, points, ctx: dict, now: float, times: list[float], bounds) -> list[float | None]:
    """What a seer says of ``times``, kept within ``bounds``; a seer with too little to go on is silent."""
    try:
        said = foresee(points, ctx, now, times) if len(points) >= 3 else None
    except (statistics.StatisticsError, ZeroDivisionError):
        said = None
    lo, hi = bounds
    return [None if v is None or math.isnan(v) else min(max(v, lo), hi) for v in said or [None] * len(times)]


def _mean_squared(said, actual) -> tuple[float, float, list[int]] | None:
    """``(mean absolute error, mean squared error, the cells scored)`` of what was said against what happened."""
    cells = [i for i, (s, a) in enumerate(zip(said, actual)) if s is not None and a is not None]
    if len(cells) < CELLS // 3:
        return None
    return statistics.fmean(abs(said[i] - actual[i]) for i in cells), statistics.fmean((said[i] - actual[i]) ** 2 for i in cells), cells


def _together(voices: list[tuple[float, list[float | None]]], n: int) -> list[tuple[float, float, float] | None]:
    """The weighted mean of what the ``voices`` (weight, values) say of each of ``n`` cells, give or take their spread."""
    out = []
    for i in range(n):
        said = [(w, values[i]) for w, values in voices if values[i] is not None]
        if not said:
            out.append(None)
            continue
        total = sum(w for w, _ in said)
        mean = sum(w * v for w, v in said) / total
        spread = math.sqrt(sum(w * (v - mean) ** 2 for w, v in said) / total)
        out.append((mean, mean - spread, mean + spread))
    return out


def council(target: str, ctx: dict, end: float, horizon: float) -> dict | None:
    """Every seer of ``target`` asked a ``horizon`` ago and now, scored, weighed and heard together."""
    points = ctx["guests"][target]
    origin = end - horizon
    past = oracle._until(points, origin)
    if len(past) < 3:
        return None
    name, unit, bounds = TARGETS[target]
    ctx = {**ctx, "target": target}
    then = _then(ctx, origin)
    hind, fore = oracle._grid(origin, end, CELLS), oracle._grid(end, end + horizon, CELLS)
    actual = oracle._on_grid(points, hind, max(3 * oracle._median_step(points), 2 * (hind[1] - hind[0])))
    skeptic = [oracle._latest(past)] * CELLS
    seers = []
    for key, title, tradition, foresee, foresees in SEERS:
        if target not in foresees:
            continue
        said_then = _ask(foresee, past, then, origin, hind, bounds)
        said_now = _ask(foresee, points, ctx, end, fore, bounds)
        score = _mean_squared(said_then, actual)
        seer = {"id": key, "name": title, "tradition": tradition, "hindcast": said_then, "forecast": said_now, "error": None, "skill": None, "weight": 0.0}
        if score:
            mae, mse, cells = score
            doubter = statistics.fmean((skeptic[i] - actual[i]) ** 2 for i in cells)
            seer.update(error=mae, mse=mse, skill=1 - mse / doubter if doubter else None)
        seers.append(seer)
    voting = [s for s in seers if s["error"] is not None and any(v is not None for v in s["forecast"])]
    total = sum(1 / (s["mse"] + EXACT) for s in voting)
    for s in voting:
        s["weight"] = 1 / (s["mse"] + EXACT) / total
    hindcast = _together([(s["weight"], s["hindcast"]) for s in voting], CELLS)
    forecast = _together([(s["weight"], s["forecast"]) for s in voting], CELLS)
    if not voting or all(f is None for f in forecast):
        return None
    scored = [i for i, (h, a) in enumerate(zip(hindcast, actual)) if h is not None and a is not None]
    shown = [(t, v) for t, v in points if t >= origin - horizon]
    shown = shown[:: max(1, len(shown) // CHART_POINTS)]
    seers.sort(key=lambda s: (-s["weight"], s["error"] is None, s["error"] or 0))
    return {
        "target": target,
        "name": name,
        "unit": unit,
        "origin": origin,
        "now": end,
        "horizon": horizon,
        "here": oracle._latest(points),
        "actual": [[t, v] for t, v in shown],
        "hindcast": [[t, *c] for t, c in zip(hind, hindcast) if c],
        "forecast": [[t, *c] for t, c in zip(fore, forecast) if c],
        "error": statistics.fmean(abs(hindcast[i][0] - actual[i]) for i in scored) if scored else None,
        "skeptic": {"value": skeptic[0], "error": statistics.fmean(abs(skeptic[i] - actual[i]) for i in scored) if scored else None},
        "seers": [
            {
                **{k: s[k] for k in ("id", "name", "tradition", "error", "skill", "weight")},
                "hindcast": [[t, v] for t, v in zip(hind, s["hindcast"]) if v is not None],
                "forecast": [[t, v] for t, v in zip(fore, s["forecast"]) if v is not None],
            }
            for s in seers
        ],
    }


def _crossing(here: float, now: float, forecast, level: float, upward: bool) -> float | None:
    """When the foreseen line first crosses ``level`` (up, or down), from ``here`` at ``now``."""
    previous = (now, here)
    for t, v, *_ in forecast:
        if (v >= level > previous[1]) if upward else (v < level <= previous[1]):
            return previous[0] + (t - previous[0]) * (level - previous[1]) / (v - previous[1])
        previous = (t, v)
    return None


def _deal(position: str, card: str, why: str) -> dict:
    number, name, meaning = ARCANA[card]
    return {"position": position, "card": card, "number": number, "numeral": ROMAN[number], "name": name, "meaning": meaning, "why": why}


def _span_card(position: str, values: list[float], hazy: bool) -> dict:
    """The card for a stretch of air: what its breath did, its veil of haze, or its stillness."""
    first, last, low, high = values[0], values[-1], min(values), max(values)
    stuffy = oracle.STUFFY_PPM
    if first < stuffy <= high:
        return _deal(position, "tower", f"the breath crosses {stuffy} ppm, and a vessel shatters")
    if low >= stuffy:
        return _deal(position, "hanged", f"the breath hangs above {stuffy} ppm throughout")
    if first >= 800 > last or last < 0.8 * first:
        return _deal(position, "star", f"the air clears, from {first:.0f} to {last:.0f} ppm")
    if hazy:
        return _deal(position, "moon", f"the haze stands at {oracle.AIRING_PM25} µg/m³ or more, and veils the window")
    if high < 600:
        return _deal(position, "sun", "the air stays fresh, below 600 ppm")
    if last > 1.2 * first:
        return _deal(position, "chariot", f"the breath drives up, from {first:.0f} to {last:.0f} ppm")
    if (high - low) > 0.15 * statistics.fmean(values) and max(first, last) < high:
        return _deal(position, "wheel", f"the breath turns, at {high:.0f} ppm")
    if abs(last - first) < 0.05 * first and high - low < 0.1 * first:
        return _deal(position, "temperance", f"the breath holds near {statistics.fmean(values):.0f} ppm")
    return _deal(position, "strength", f"the breath moves from {first:.0f} to {last:.0f} ppm, and bears it")


def _spread(breath: dict, haze: dict | None, souls: float | None) -> list[dict]:
    """Past, present and future, each card dealt by the numbers: what the air did over the hindcast, how it is now,
    and what the council foresees."""
    def hazy_over(series):
        return bool(haze) and any(v >= oracle.AIRING_PM25 for v in series)

    past = [v for t, v in breath["actual"] if breath["origin"] <= t <= breath["now"]] or [breath["here"]]
    hour = [v for t, v in breath["actual"] if t >= breath["now"] - 3600] or [breath["here"]]
    future = [breath["here"]] + [v for _, v, *_ in breath["forecast"]]
    here = breath["here"]
    if souls is not None and souls >= 1.5:
        present = _deal("Present", "lovers", f"{souls:.1f} souls share the air")
    elif souls is not None and souls < 0.3:
        present = _deal("Present", "hermit", "nobody breathes here but the air itself")
    elif here >= oracle.STUFFY_PPM:
        present = _deal("Present", "devil", f"the breath is bound above {oracle.STUFFY_PPM} ppm, at {here:.0f}")
    else:
        present = _span_card("Present", hour, hazy_over([haze["here"]] if haze else []))
    return [
        _span_card("Past", past, hazy_over([v for t, v in haze["actual"] if t >= haze["origin"]] if haze else [])),
        present,
        _span_card("Future", future, hazy_over([v for _, v, *_ in haze["forecast"]] if haze else [])),
    ]


def unify(breath: dict | None, haze: dict | None, outdoor_pm25: float | None, souls: float | None = None) -> dict:
    """The unified prophecy, read from the councils of the breath and of the haze: what they foresee, the one piece of
    advice that matters (when to air the room, if the haze allows it), and what the council itself reveals."""
    lead = breath or haze
    end, horizon = lead["now"], lead["horizon"]
    upto = _when(end + horizon, end, word="by")
    lines, counsel = [], ""
    headline = ""
    if breath:
        here, forecast = breath["here"], breath["forecast"]
        last = forecast[-1][1]
        rise = _crossing(here, end, forecast, oracle.STUFFY_PPM, upward=True)
        clear = _crossing(here, end, forecast, 0.95 * oracle.STUFFY_PPM, upward=False) if here >= oracle.STUFFY_PPM else None
        peak = max(forecast, key=lambda c: c[1])
        voting = sum(s["weight"] > 0 for s in breath["seers"])
        text = (
            f"The council of {voting} seer{'s' if voting != 1 else ''}, each weighed by how well it foresaw the last "
            f"{_duration(horizon)}, foresees your breath at {last:.0f} ppm {upto}"
        )
        if rise:
            text += f", crossing {oracle.STUFFY_PPM} ppm {_when(rise, end)}"
            headline = f"{oracle.STUFFY_PPM} ppm {_when(rise, end)}"
        elif clear:
            text += f", clearing below {0.95 * oracle.STUFFY_PPM:.0f} ppm {_when(clear, end)}"
            headline = f"Clearing {_when(clear, end, word='by')}"
        if peak[1] > max(here, last) + 25:
            text += f", at its heaviest {_when(peak[0], end)} ({peak[1]:.0f} ppm)"
        lines.append(text + ".")
        headline = headline or (f"{last:.0f} ppm {upto}" if abs(last - here) >= 25 else f"Steady near {here:.0f} ppm")
        stuffy = rise or here >= oracle.STUFFY_PPM or peak[1] >= oracle.STUFFY_PPM
        deadline = rise or (peak[0] if peak[1] >= oracle.STUFFY_PPM else end + horizon)
    if haze:
        cells = [(t, v) for t, v, *_ in haze["forecast"]]
        thinnest = min(cells, key=lambda c: c[1])
        lines.append(
            f"The haze at your door: {cells[-1][1]:.0f} µg/m³ {upto}, thinnest {_when(thinnest[0], end)} ({thinnest[1]:.0f})."
        )
        headline = headline or f"Haze {cells[-1][1]:.0f} µg/m³ {upto}"
    if breath and stuffy:
        if haze:
            clean = [(t, v) for t, v in cells if v < oracle.AIRING_PM25 and t <= deadline]
            now_clean = outdoor_pm25 is not None and not oracle.hazy(outdoor_pm25)
            before = f", before your breath crosses {oracle.STUFFY_PPM} ppm {_when(rise, end)}" if rise else ""
            if now_clean or (clean and clean[0] == cells[0]):
                counsel = f"Open a window now, while the haze is thin{before}."
            elif clean:
                counsel = f"Air the room {_when(clean[0][0], end)}, when the haze thins to {clean[0][1]:.0f} µg/m³{before}."
            else:
                counsel = (
                    f"Keep the windows sealed: the haze stays at {oracle.AIRING_PM25} µg/m³ or more {_when(deadline, end, word='until')}. "
                    "Thin the crowd, and let the purifier sing."
                )
        else:
            counsel = oracle.airing(outdoor_pm25)
            if rise and not oracle.hazy(outdoor_pm25):
                counsel += f" Do it {_when(rise, end, word='by')}."
    elif breath:
        counsel = f"No airing is due: your breath stays below {oracle.STUFFY_PPM} ppm {_when(end + horizon, end, word='until')}."
        if haze and not oracle.hazy(outdoor_pm25) and (thick := next((t for t, v in cells if v >= oracle.AIRING_PM25), None)):
            counsel += f" If a window is open, close it {_when(thick, end)}, when the haze returns."
    elif haze:
        counsel = "Keep the windows shut while the haze lasts." if oracle.hazy(cells[0][1]) else "The haze allows an open window, for now."
    revealed = _revelation(lead)
    return {
        "headline": headline,
        "prophecy": {"foretold": " ".join(lines), "counsel": counsel, "revealed": revealed},
        "spread": _spread(breath, haze, souls) if breath else [],
    }


def _revelation(council_: dict) -> str:
    """What the council reveals of itself: whom it trusts, whether it agrees, and the number of the future."""
    unit = council_["unit"]
    voting = [s for s in council_["seers"] if s["weight"] > 0]
    best = voting[0]
    worst = max(voting, key=lambda s: s["error"])
    lines = [
        f"The most trusted seer is {best['name']}, off by {best['error']:.0f} {unit} over the last {_duration(council_['horizon'])}"
        + (f", {best['skill']:+.0%} on the Skeptic" if best["skill"] is not None else "")
        + (f"; the least, {worst['name']}, off by {worst['error']:.0f}." if worst is not best else ".")
    ]
    weights = {t: sum(s["weight"] for s in voting if s["tradition"] == t) for t in ("Oracle", "Tree of Life")}
    if all(weights.values()):
        ahead = max(weights, key=weights.get)
        lines.append(
            f"For now the Oracle's seers carry {weights['Oracle']:.0%} of the weight and the Tree of Life's "
            f"{weights['Tree of Life']:.0%}: " + ("the planets outrank the letters." if ahead == "Oracle" else "the letters outrank the planets.")
        )
    error, doubt = council_["error"], council_["skeptic"]["error"]
    if error is not None and doubt is not None and doubt < error:
        lines.append(
            f"Yet the Skeptic, who expected nothing to change, came nearer than the council ({doubt:.0f} {unit} off, "
            f"against {error:.0f}): a humbling hour for the occult."
        )
    here = council_["here"]
    ups = [s for s in voting if s["forecast"] and s["forecast"][-1][1] > here]
    if len(voting) >= 3 and len(ups) in (0, len(voting)):
        lines.append(
            f"All {len(voting)} seers foresee it {'rising' if ups else 'falling'}, and the Sanhedrin held that a verdict "
            "nobody argued against acquits: trust this one less."
        )
    elif len(voting) >= 3:
        lines.append(f"{len(ups)} of {len(voting)} seers foresee it rising.")
    future = round(council_["forecast"][-1][1])
    if 1 <= future <= 999_999:
        word, translit, meaning = kabbalah._nearest_word(future, kabbalah.WORDS)
        lines.append(f"The air to come, {future} {unit}, is written {kabbalah.hebrew_numeral(future)}, nearest {word} ({translit}, {meaning}).")
    return " ".join(lines)


def analyze(co2, start: float, end: float, others=None, regions=None, placements=(), home=None, outdoor_pm25: float | None = None) -> dict:
    """The council of seers over the window from ``start`` to ``end``, and the unified prophecy it gives.

    The series are as ``oracle.analyze`` takes them; ``outdoor_pm25`` is the latest outdoor PM2.5, if known,
    so that the prophecy never opens a window into the haze.
    """
    pool = {BREATH: co2, **(others or {})}
    guests = {name: pool[name] for name in oracle.GUESTS if len(pool.get(name) or ()) >= 2}
    present = [t for t in TARGETS if t in guests]
    disclaimer = "Strictly pseudo-prophetic. Every forecast is computed honestly, and scored honestly; every prophecy is not."
    if not present:
        return {"councils": [], "spread": [], "disclaimer": "The council needs readings to foresee anything."}
    span = min(guests[t][-1][0] - guests[t][0][0] for t in present)
    horizon = min(max(span * HORIZON_SHARE, HORIZON[0]), HORIZON[1])
    ctx = {
        "guests": guests,
        "regions": regions or {},
        "wind_direction": (others or {}).get("outdoor_wind_direction") or [],
        "placements": placements,
        "home": home,
        "start": start,
    }
    councils = {t: c for t in present if (c := council(t, ctx, end, horizon))}
    if not councils:
        return {"councils": [], "spread": [], "disclaimer": "The seers need a longer window to be put to the test."}
    souls = oracle.souls(co2, placements, end)["souls"] if co2 else None
    unified = unify(councils.get(BREATH), councils.get(HAZE), outdoor_pm25, souls)
    return {
        "id": "prophecy",
        "title": "The unified prophecy",
        **unified,
        "horizon": horizon,
        "now": end,
        "councils": list(councils.values()),
        "certainty": oracle._pick(CERTAINTIES, unified["headline"]),
        "disclaimer": disclaimer,
    }

