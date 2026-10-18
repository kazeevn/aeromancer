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
by hand to speed 1 for 40 minutes or more. The forecast assumes the filter
wears with age, ``health = exp(-age / tau)``, with ``tau`` fitted to the tests
since the filter was replaced (docs/blueair.md#filter-health).
"""

from __future__ import annotations

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


@dataclass
class Settings:
    room_volume: float  # m³ of air in the closed-off room, closed furniture taken out
    cadr: float  # m³/h, a fresh filter's clean air delivery at speed 1
    cadr_error: float = 0.15  # relative half-width of the range cadr may be off by
    background: tuple[float, float] = (0.3, 1.0)  # /h, the range of the loss with the fan off
    replace_at: float = 0.5  # health at which the filter is due


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
    except KeyError as e:
        raise ValueError(f"{path}: [filter] lacks {e.args[0]!r}") from None
    except (TypeError, ValueError):
        raise ValueError(f"{path}: [filter] wants numbers, and background as [low, high]") from None
    if settings.room_volume <= 0 or settings.cadr <= 0 or not 0 < settings.replace_at < 1:
        raise ValueError(f"{path}: [filter] room_volume and cadr must be positive, replace_at between 0 and 1")
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


def forecast(tests: list[tuple[float, float, float]], replaced: float, settings: Settings) -> dict | None:
    """When health falls to ``replace_at`` if it goes as ``exp(-age / tau)``.

    ``tests`` are ``(ts, health, sd of its log)``. ``1 / tau`` is fitted
    through the origin on ``-log health``, weighted by the tests' spread; the
    early and late dates are its 90 % range, late None when that range allows
    no wear at all.
    """
    pairs = [((ts - replaced) / 86400, -math.log(h), sd) for ts, h, sd in tests if h > 0 and sd > 0]
    pairs = [p for p in pairs if p[0] > 0]
    if not pairs:
        return None
    weight = sum(age * age / (sd * sd) for age, _, sd in pairs)
    k = sum(age * y / (sd * sd) for age, y, sd in pairs) / weight
    k_sd = 1 / math.sqrt(weight)
    due_age = math.log(1 / settings.replace_at)

    def due(rate):
        return replaced + due_age / rate * 86400 if rate > 0 else None

    return {
        "tau_days": 1 / k if k > 0 else None,
        "due": due(k),
        "due_early": due(k + Z90 * k_sd),
        "due_late": due(k - Z90 * k_sd),
    }


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
        "forecast": forecast(healths, since, settings) if settings and since else None,
    }
