"""How worn the purifier's filter is, from decay tests, and when it will be due.

A decay test: close off the room the purifier stands in, fill it with outdoor
haze through an open window with the fan off, shut the window, and set the fan
to speed 1 by hand for an hour. The particles then fall as
``C(t) = C_ss + A exp(-rate t)``, and

    health = (rate - background) * room_volume / cadr

is the filter's clean air delivery as a share of a fresh one's: 1 new, 0.5
due (the end of life GB/T 18801 defines). ``background`` is the loss to leaks
and walls alone. The purifier's own sensor can't measure it: with the fan off
it reads its own pocket of air, not the room. So it is taken as a range.

Tests are found in the recording by the fan's settings: set by hand to 0, then
by hand to speed 1 for 40 minutes or more. Two forecasts, each fitted to the
tests since the filter was replaced: by age, ``health = exp(-age / tau)``, and
by what it caught, ``health = exp(-caught / m0)``, ``caught`` being the
particles a fresh filter would have taken from the air the purifier moved
(docs/blueair.md#filter-health).
"""

from __future__ import annotations

import bisect
import math
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import blueair
from .store import Store

PM = blueair.PREFIX + "pm25"
FAN = blueair.PREFIX + "fan_speed"
AUTO = blueair.PREFIX + "auto_mode"
REPLACED = blueair.PREFIX + "filter_replaced"
EXPIRED = blueair.PREFIX + "filter_expired"

MIXING = 600  # s after the first upload at speed 1 left out of the fit: the room is still mixing
MIN_RUN = 2100  # s from the first to the last upload at speed 1, i.e. about 40 minutes at it
MIN_POINTS = 6
MIN_DROP = 10.0  # µg/m³ from the first fitted point to the last
RATES = (0.05, 30.0)  # /h, the range searched
Z90 = 1.645  # half the width of a 90 % range, in standard deviations
APP_DAYS = 180
# Auto mode's PM2.5 thresholds for speeds 2 and 3, for the speed where none was recorded (docs/blueair.md#filter-health).
AUTO_THRESHOLDS = (23.5, 33.5)
SPEED_KEPT = 1800  # s a recorded fan speed stands for uploads that came without one
MAX_STEP = 600  # s an upload's PM2.5 stands for at most: longer gaps the purifier was off or unseen
PACE = 7 * 86400  # s of catching the forecast by what it caught carries on at


@dataclass
class Settings:
    room_volume: float  # m³ of air in the closed-off room, closed furniture taken out
    cadr: float  # m³/h, a fresh filter's clean air delivery at speed 1
    cadr_error: float = 0.15  # relative half-width of the range cadr may be off by
    background: tuple[float, float] = (0.3, 1.0)  # /h, the range of the loss with the fan off
    replace_at: float = 0.5  # health at which the filter is due
    airflow: tuple[float, ...] | None = None  # m³/h at speeds 1, 2, ...; needed for the forecast by what it caught


@dataclass
class Test:
    start: float  # the first upload at speed 1
    end: float  # the last
    points: int  # uploads fitted
    rate: float  # /h
    rate_error: float  # /h, one standard error
    steady: float  # µg/m³, C_ss


def load_settings(path) -> Settings | None:
    """The ``[filter]`` table of the purifier's config, or None when there is none."""
    try:
        with Path(path).open("rb") as f:
            table = tomllib.load(f).get("filter")
    except FileNotFoundError:
        return None
    if table is None:
        return None
    try:
        settings = Settings(float(table["room_volume"]), float(table["cadr"]))
        if "cadr_error" in table:
            settings.cadr_error = float(table["cadr_error"])
        if "background" in table:
            lo, hi = table["background"]
            settings.background = (float(lo), float(hi))
        if "replace_at" in table:
            settings.replace_at = float(table["replace_at"])
        if "airflow" in table:
            settings.airflow = tuple(float(q) for q in table["airflow"])
    except KeyError as e:
        raise ValueError(f"{path}: [filter] lacks {e.args[0]!r}") from None
    except (TypeError, ValueError):
        raise ValueError(f"{path}: [filter] wants numbers, and background as [low, high]") from None
    if settings.room_volume <= 0 or settings.cadr <= 0 or not 0 < settings.replace_at < 1:
        raise ValueError(f"{path}: [filter] room_volume and cadr must be positive, replace_at between 0 and 1")
    if settings.airflow is not None and (not settings.airflow or min(settings.airflow) <= 0):
        raise ValueError(f"{path}: [filter] airflow must list positive numbers, speed 1 first")
    return settings


def app_days_left(ticks: float) -> int:
    """What the purifier's app shows as the filter's days left, from the filter counter (docs/blueair.md)."""
    return APP_DAYS - math.floor(ticks * 5 / 1444)


def _linear(t, y, rate):
    """The best ``(C_ss, A)`` for ``rate``, and the squared error left."""
    n = len(t)
    e = [math.exp(-rate * ti) for ti in t]
    se, see = sum(e), sum(x * x for x in e)
    sy, sey = sum(y), sum(a * b for a, b in zip(e, y))
    det = n * see - se * se
    if det <= 1e-12:
        return None
    amp = (n * sey - se * sy) / det
    steady = (sy - amp * se) / n
    return steady, amp, sum((yi - steady - amp * ei) ** 2 for yi, ei in zip(y, e))


def fit_decay(points: list[tuple[float, float]]) -> tuple[float, float, float] | None:
    """Fit ``C_ss + A exp(-rate t)`` to ``(ts, value)`` points: ``(rate /h, its standard error, C_ss)``, or None.

    For a given rate the best C_ss and A are a linear fit, so only the rate is
    searched: on a grid, then by golden section around the best point.
    """
    if len(points) < 4:
        return None
    t0 = points[0][0]
    t = [(ts - t0) / 3600 for ts, _ in points]
    y = [v for _, v in points]

    def sse(u):
        fit = _linear(t, y, math.exp(u))
        return fit[2] if fit else math.inf

    lo, hi = (math.log(r) for r in RATES)
    grid = [lo + (hi - lo) * k / 80 for k in range(81)]
    best = min(range(len(grid)), key=lambda k: sse(grid[k]))
    a, b = grid[max(0, best - 1)], grid[min(len(grid) - 1, best + 1)]
    g = (math.sqrt(5) - 1) / 2
    for _ in range(60):
        c, d = b - g * (b - a), a + g * (b - a)
        if sse(c) < sse(d):
            b = d
        else:
            a = c
    rate = math.exp((a + b) / 2)
    fit = _linear(t, y, rate)
    if fit is None or fit[1] <= 0 or not RATES[0] * 1.01 < rate < RATES[1] / 1.01:
        return None
    steady, amp, err = fit
    # Standard error from the Jacobian of (C_ss, A, rate), with the residuals' scale.
    cols = [[1.0] * len(t), [math.exp(-rate * ti) for ti in t], [-amp * ti * math.exp(-rate * ti) for ti in t]]
    m = [[sum(p * q for p, q in zip(ci, cj)) for cj in cols] for ci in cols]
    det = (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )
    dof = len(t) - 3
    if det <= 0 or dof <= 0:
        return None
    variance = err / dof * (m[0][0] * m[1][1] - m[0][1] * m[1][0]) / det
    return rate, math.sqrt(max(variance, 0.0)), steady


def _test(run: list[tuple[float, float]]) -> Test | None:
    start, end = run[0][0], run[-1][0]
    if end - start < MIN_RUN:
        return None
    points = [p for p in run if p[0] >= start + MIXING]
    if len(points) < MIN_POINTS or points[0][1] - points[-1][1] < MIN_DROP:
        return None
    fit = fit_decay(points)
    return Test(start, end, len(points), *fit) if fit else None


def find_tests(store: Store, start: float, end: float) -> list[Test]:
    """The decay tests from ``start`` to ``end``: uploads at speed 1 set by hand, right after the fan was set off by hand."""
    fan = {ts: v for ts, _, v in store.rows(FAN, start, end)}
    auto = {ts: v for ts, _, v in store.rows(AUTO, start, end)}
    tests, run, filled = [], [], False
    # The settings are stored at each upload the poller saw as it came; uploads filled in after a gap have none.
    for ts, _, value in store.rows(PM, start, end) + [(math.inf, PM, math.nan)]:
        setting = (fan.get(ts), auto.get(ts))
        if setting == (1.0, 0.0) and (run or filled):
            run.append((ts, value))
            continue
        if run and (test := _test(run)):
            tests.append(test)
        run, filled = [], setting == (0.0, 0.0)
    return tests


def health(rate: float, rate_error: float, settings: Settings) -> tuple[float, float]:
    """``(health, standard deviation of its log)`` from a test's decay rate.

    The background loss and the cadr's error are uniform ranges; the spread is
    added up in quadrature, on a log scale since cadr scales the health.
    """
    lo, hi = settings.background
    gain = rate - (lo + hi) / 2
    if gain <= 0:
        return 0.0, math.nan
    gain_sd = math.hypot(rate_error, (hi - lo) / math.sqrt(12))
    return gain * settings.room_volume / settings.cadr, math.hypot(gain_sd / gain, settings.cadr_error / math.sqrt(3))


def caught(store: Store, start: float, end: float, settings: Settings) -> list[tuple[float, float]]:
    """``(ts, mg)``: what a fresh filter would have caught from ``start`` to each upload until ``end``.

    Each upload's PM2.5 stands until the next one (at most ``MAX_STEP``), at the
    fresh clean air delivery of the fan's speed: ``cadr`` scaled by the airflow.
    Uploads without a recorded speed take the last one recorded within
    ``SPEED_KEPT``, or else the one auto mode would pick for their PM2.5.
    """
    fan = {ts: v for ts, _, v in store.rows(FAN, start, end)}
    efficiency = settings.cadr / settings.airflow[0]
    out, total, last, speed, speed_ts = [], 0.0, None, None, -math.inf
    for ts, _, pm in store.rows(PM, start, end):
        if ts in fan:
            speed, speed_ts = fan[ts], ts
        elif ts - speed_ts > SPEED_KEPT:
            speed = 1 + sum(pm >= t for t in AUTO_THRESHOLDS)
        if last is not None:
            ts0, pm0, s0 = last
            flow = settings.airflow[min(int(s0), len(settings.airflow)) - 1] if s0 >= 1 else 0.0
            total += pm0 * efficiency * flow * min(ts - ts0, MAX_STEP) / 3600 / 1000  # µg -> mg
        out.append((ts, total))
        last = (ts, pm, speed)
    return out


def _wear_rate(points: list[tuple[float, float, float]]) -> tuple[float, float] | None:
    """``(k, its sd)`` of ``health = exp(-k x)`` through ``(x, health, sd of its log)`` points, weighted by their spread."""
    pairs = [(x, -math.log(h), sd) for x, h, sd in points if x > 0 and h > 0 and sd > 0]
    if not pairs:
        return None
    weight = sum(x * x / (sd * sd) for x, _, sd in pairs)
    return sum(x * y / (sd * sd) for x, y, sd in pairs) / weight, 1 / math.sqrt(weight)


def _due(fit, x_now: float, now: float, x_per_day: float, settings: Settings) -> dict | None:
    """When ``exp(-k x)`` reaches ``replace_at``, with x going on at ``x_per_day``: the fit's 90 % range.

    Late is None when the range allows no wear at all.
    """
    if fit is None or x_per_day <= 0:
        return None
    k, k_sd = fit
    x_due = math.log(1 / settings.replace_at)

    def due(rate):
        return now + max(0.0, x_due / rate - x_now) / x_per_day * 86400 if rate > 0 else None

    return {
        "scale": 1 / k if k > 0 else None,
        "now": math.exp(-k * x_now),
        "due": due(k),
        "due_early": due(k + Z90 * k_sd),
        "due_late": due(k - Z90 * k_sd),
    }


def forecast(
    tests: list[tuple[float, float, float]], replaced: float, now: float, settings: Settings, caught_mg=None
) -> dict:
    """When health falls to ``replace_at``, by age and by what the filter caught.

    ``tests`` are ``(ts, health, sd of its log)``. ``k`` is fitted through the
    origin on ``-log health``. By age, ``scale`` is tau in days; by what it
    caught, m0 in mg, with the catch going on at its pace over the last
    ``PACE`` (at the average pace since the replacement it would be the age
    forecast again). ``caught_mg`` is the ``(ts, mg)`` series from ``caught``.
    """
    age_now = (now - replaced) / 86400
    out = {"age": _due(_wear_rate([((ts - replaced) / 86400, h, sd) for ts, h, sd in tests]), age_now, now, 1.0, settings)}
    if caught_mg:
        times = [ts for ts, _ in caught_mg]

        def at(ts):
            i = max(0, bisect.bisect_right(times, ts) - 1)
            return caught_mg[i][1]

        mg_now = caught_mg[-1][1]
        days = min(PACE, now - replaced) / 86400
        pace = (mg_now - at(now - days * 86400)) / days if days > 0 else 0.0
        fit = _wear_rate([(at(ts), h, sd) for ts, h, sd in tests])
        out["caught"] = _due(fit, mg_now, now, pace, settings)
        out["caught_mg"] = mg_now
        out["caught_mg_per_day"] = pace
    return out


def status(store: Store, settings: Settings | None, now: float | None = None) -> dict:
    """The filter's state for the dashboard: the app's timer, the tests since the replacement, the forecast."""
    now = time.time() if now is None else now
    replaced = store.latest_of(REPLACED)
    counter = store.latest_of(blueair.FILTER_COUNTER)
    expired = store.latest_of(EXPIRED)
    # Without a recorded replacement, at least as long ago as the filter counter has run.
    since = replaced[0] if replaced else (counter[0] - counter[1] * blueair.TICK if counter else 0.0)
    tests, healths = [], []
    for t in find_tests(store, since, now):
        row = {"start": t.start, "end": t.end, "points": t.points, "rate": t.rate, "rate_error": t.rate_error}
        if settings:
            h, sd = health(t.rate, t.rate_error, settings)
            spread = math.exp(Z90 * sd) if math.isfinite(sd) else None
            row.update(health=h, health_low=h / spread if spread else 0.0, health_high=h * spread if spread else None)
            healths.append((t.start, h, sd))
        tests.append(row)
    return {
        "replaced": since if (replaced or counter) else None,
        "replaced_recorded": replaced is not None,
        "app_days_left": app_days_left(counter[1]) if counter else None,
        "expired": bool(expired[1]) if expired else None,
        "configured": settings is not None,
        "replace_at": settings.replace_at if settings else None,
        "tests": tests,
        "forecast": forecast(healths, since, now, settings, caught(store, since, now, settings) if settings.airflow else None)
        if settings and since
        else None,
    }
