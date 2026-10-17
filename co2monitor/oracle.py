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
import statistics
from datetime import datetime

from . import astro

PHI = (1 + 5**0.5) / 2
SCHUMANN_HZ = 7.83

# Upper CO2 bound (ppm), name, Sanskrit name, reading.
CHAKRAS = (
    (450, "Crown", "Sahasrara", "Transcendent. Indistinguishable from outdoor air, or the sensor is outside."),
    (600, "Third Eye", "Ajna", "Clairvoyant ventilation. You can see the future, and it is well aired."),
    (800, "Throat", "Vishuddha", "Clear communication between your lungs and the atmosphere."),
    (1000, "Heart", "Anahata", "Warm, loving, slightly shared air."),
    (1400, "Solar Plexus", "Manipura", "Willpower is high. Oxygen is less so."),
    (2000, "Sacral", "Svadhishthana", "Creative energy is pooling near the ceiling."),
    (math.inf, "Root", "Muladhara", "Deeply grounded. Possibly asleep. Open a window."),
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


def _chakra_for(ppm: float):
    return next(c for c in CHAKRAS if ppm < c[0])


def chakra_of(ppm: float) -> str:
    return _chakra_for(ppm)[1]


def chakra_residency(co2):
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
        f"({CHAKRAS[dominant][2]}). {CHAKRAS[dominant][3]}",
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
    intervals = astro.mercury_retrograde_intervals(start, end)
    stuffy = [t for t, v in co2 if v >= 1000]
    blamed = sum(any(a <= t <= b for a, b in intervals) for t in stuffy)
    if not stuffy:
        blame = "No stuffy air (≥1000 ppm) to blame on anyone. Mercury is bored."
    elif blamed:
        blame = f"{blamed / len(stuffy):.0%} of your stuffy air (≥1000 ppm) is attributable to Mercury."
    else:
        blame = "Mercury was direct the whole time, so the stuffy air is entirely your own doing."
    when = datetime.fromtimestamp(station).strftime("%b %-d")
    return {
        "id": "mercury",
        "title": "Mercury",
        "headline": "Retrograde ℞" if retro_now else "Direct",
        "body": f"{blame} Mercury stations {turn} on {when}.",
        "retrograde": retro_now,
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


def horoscope(co2, end, findings):
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
    advice = (
        "With Mercury retrograde, avoid signing contracts in poorly ventilated rooms."
        if by_id["mercury"]["retrograde"]
        else f"Under a {moon_name if moon_name.endswith('Moon') else moon_name + ' Moon'}, it is an auspicious time to "
        + _pick(("air out the bedroom.", "water a plant.", "breathe more quietly.", "stand near a window."), day, "advice")
    )
    lucky = round(statistics.fmean(last_hour or [v for _, v in co2]))
    return {
        "id": "horoscope",
        "title": "Today's horoscope",
        "headline": datetime.fromtimestamp(end).strftime("%A, %B %-d"),
        "body": f"{opening} {middle} {advice} Lucky ppm: {lucky}.",
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


def analyze(
    co2: list[tuple[float, float]],
    temperature: list[tuple[float, float]],
    start: float,
    end: float,
    signals: dict[str, list[tuple[float, float]]] | None = None,
) -> dict:
    """All series are ``(ts, value)`` lists in time order; ``signals`` maps ``op_XX`` names to theirs."""
    if not co2:
        return {"findings": [], "disclaimer": "The Oracle needs CO2 readings to divine anything."}
    findings = [
        aura(co2, temperature),
        lunar(co2, end),
        mercury(co2, start, end),
        chakra_residency(co2),
        schumann(co2),
        golden_ratio(co2),
        numerology(co2),
        zodiac(co2, temperature, end),
        voices(signals or {}, co2, temperature, start, end),
    ]
    findings.append(horoscope(co2, end, findings))
    for f in findings:
        f["certainty"] = _pick(CERTAINTIES, f["id"], f["headline"])
    return {
        "findings": findings,
        "disclaimer": "Strictly pseudo-scientific. Every number is computed honestly; every conclusion is not.",
    }
