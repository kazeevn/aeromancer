import json
import math
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from aeromancer import astro, kabbalah, lore, nea, oracle, prophecy, server
from aeromancer.device import Reading
from aeromancer.store import Placement, Store

START = 1_790_000_000.0
HOUR = 3600
DAY = 86400
PLACED = [Placement(1, 0, "zytemp", "living room", "table"), Placement(2, 0, "blueair", "bedroom", "")]


def ts(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


def daily(t, peak_utc_hour=8, mean=700, amplitude=200):
    return mean + amplitude * math.cos(2 * math.pi * (t - peak_utc_hour * HOUR) / DAY)


def series(f, start, end, step=300):
    return [(start + i * step, f(start + i * step)) for i in range(int((end - start) // step) + 1)]


def context(target="co2", guests=None, start=START, **extra):
    return {"target": target, "guests": guests or {}, "regions": {}, "wind_direction": [], "placements": (), "home": None, "start": start, **extra}


def ahead(now, hours=6, cells=24):
    return oracle._grid(now, now + hours * HOUR, cells)


class SeersTest(unittest.TestCase):
    """Each seer, on a series whose future is known."""

    def test_the_clock_carries_the_daily_rhythm_on(self):
        points = series(daily, START, START + 2 * DAY)
        now = points[-1][0]
        times = ahead(now)
        for got, t in zip(oracle.foresee_clock(points, context(), now, times), times):
            self.assertAlmostEqual(got, daily(t), delta=1)
        self.assertIsNone(oracle.foresee_clock(points[-100:], context(), now, times))  # less than a day: no rhythm yet

    def test_schumann_sounds_the_strongest_rhythm_on(self):
        wave = lambda t: 800 + 100 * math.sin(2 * math.pi * (t - START) / (6 * HOUR))
        points = series(wave, START, START + 2 * DAY)
        now = points[-1][0]
        times = ahead(now)
        for got, t in zip(oracle.foresee_schumann(points, context(), now, times), times):
            self.assertAlmostEqual(got, wave(t), delta=5)

    def test_the_souls_breathe_on(self):
        souls, air_changes, volume = 1.5, 1.0, oracle.ROOM_VOLUMES["living room"]
        settle = oracle.OUTDOOR_CO2 + souls * oracle.EXHALED * 1000 / (air_changes * volume)
        level = lambda t: settle + (1500 - settle) * math.exp(-air_changes * (t - START) / HOUR)  # a crowd's air, airing out
        points = series(level, START, START + 2 * HOUR, 60)
        now = points[-1][0]
        times = ahead(now, 2)
        said = oracle.foresee_souls(points, context(placements=PLACED), now, times)
        for got, t in zip(said, times):
            self.assertAlmostEqual(got, level(t), delta=15)
        f = oracle.souls(points, PLACED, now)
        self.assertAlmostEqual(f["settles"], settle, delta=30)
        self.assertIn("settles at", f["prophecy"]["foretold"])

    def test_the_choir_resolves_to_its_tonic(self):
        points = [(START + i * 60, 500.0) for i in range(600)] + [(START + (600 + i) * 60, 1100.0) for i in range(60)]
        now = points[-1][0]
        said = oracle.foresee_choir(points, context(), now, ahead(now, 24))
        tonic = sum(v for _, v in points) / len(points)
        self.assertTrue(all(a > b for a, b in zip(said, said[1:])))  # coming home, always downhill
        self.assertAlmostEqual(said[-1], tonic, delta=5)

    def test_markov_chains_learn_the_alternation(self):
        anchor = START + 600 * 60
        # Ten minutes at 900 ppm, ten at 500, and so on, the last ten at 900.
        points = [(anchor - 60 * k, 900.0 if k // 10 % 2 == 0 else 500.0) for k in range(600)][::-1]
        times = oracle._grid(anchor, anchor + 24 * 600, 24)
        for foresee in (oracle.foresee_chakra, kabbalah.foresee_tree):
            said = foresee(points, context(), anchor, times)
            self.assertEqual([round(v) for v in said[:4]], [500, 900, 500, 900], foresee.__name__)
        stale = foresee(points, context(), anchor + 1800, oracle._grid(anchor + 1800, anchor + 1800 + 24 * 600, 24))
        self.assertIsNotNone(stale)  # readings that stopped a while ago still foretell

    def test_mercury_carries_yesterday_and_brings_back_the_past_reversed(self):
        ramp = lambda t: (t - START) / HOUR
        for when, expected in (
            ("2024-08-15", lambda now, t: ramp(2 * now - t)),  # retrograde: the last hours, in reverse
            ("2024-09-25", lambda now, t: ramp(t - DAY)),  # direct and free of shadow: yesterday again
        ):
            now = ts(when)
            points = [(now - 2 * DAY + i * 600, ramp(now - 2 * DAY + i * 600)) for i in range(2 * 144 + 1)]
            times = ahead(now)
            for got, t in zip(oracle.foresee_mercury(points, context(), now, times), times):
                self.assertAlmostEqual(got, expected(now, t), places=6, msg=when)

    def test_the_golden_spiral_retraces_by_phi(self):
        rise = [(START + i * 60, 400 + 600 * i / 360) for i in range(361)]  # six hours up, to 1000
        fall = [(START + (361 + i) * 60, 1000 - 150 * (i + 1) / 60) for i in range(60)]  # and the first hour down
        points = rise + fall
        now = points[-1][0]
        turns = oracle._spiral(points, now + DAY)
        (t0, v0), (t1, v1), (t2, v2) = turns[:3]
        self.assertAlmostEqual(v2, v1 - (v1 - v0) / oracle.PHI, places=6)
        self.assertAlmostEqual(t2 - t1, (t1 - t0) / oracle.PHI, places=6)  # the fall is 1/φ of the rise
        self.assertAlmostEqual(v1, 1000, delta=20)
        said = oracle.foresee_golden(points, context(), now, ahead(now, 6, 72))
        self.assertAlmostEqual(min(said), v2, delta=5)

    def test_the_i_ching_turns_its_old_lines(self):
        now = START // HOUR * HOUR + 10 * HOUR + 1800
        steady = [(now - 6 * HOUR + i * 60, 600 + i * 100 / 60) for i in range(360)]  # 100 ppm an hour: young yang
        said = oracle.foresee_iching(steady, context(), now, ahead(now, 3, 6))
        here = oracle._latest(steady)
        self.assertAlmostEqual(said[0], here + 100 * 0.25, delta=1)  # a quarter of the way through its hour
        self.assertAlmostEqual(said[-1], here + 100, delta=1)  # and no further once the hour is over
        jump = steady[:-90] + [(t, v + 15 * i) for i, (t, v) in enumerate(steady[-90:])]  # far more than usual: old yang
        self.assertLess(oracle.foresee_iching(jump, context(), now, ahead(now, 3, 6))[-1], oracle._latest(jump))

    def test_the_society_follows_its_leader(self):
        wave = lambda t: math.sin((t - START) / 5000)
        leader = series(wave, START, START + 2 * DAY)
        follower = [(t, 100 + 2 * wave(t - 1800)) for t, _ in leader]  # half an hour behind
        now = follower[-1][0]
        times = oracle._grid(now, now + 1800, 6)
        said = oracle.foresee_society(follower, context(guests={"blueair_voc": leader}), now, times)
        for got, t in zip(said, times):
            self.assertAlmostEqual(got, 100 + 2 * wave(t - 1800), delta=0.05)
        later = oracle.foresee_society(follower, context(guests={"blueair_voc": leader}), now, [now + 3 * HOUR])
        self.assertEqual(later, [None])  # the leader has not yet said that much

    def test_the_elements_flow_into_your_door(self):
        times = [START + 1800 + i * HOUR for i in range(72)]
        wave = [50 + 30 * math.sin(i / 4) for i in range(80)]
        regions = {r: [(t, 60 + 10 * math.cos(i * k)) for i, t in enumerate(times)] for k, r in enumerate(lore.ELEMENTS, 1)}
        regions["west"] = [(t, wave[i + 2]) for i, t in enumerate(times)]  # two hours ahead of the door
        regions["central"] = door = [(t, wave[i]) for i, t in enumerate(times)]
        now = times[-1]
        said = oracle.foresee_elements(door, context("outdoor_pm25", regions=regions), now, [now + HOUR, now + 2 * HOUR, now + 3 * HOUR])
        self.assertAlmostEqual(said[0], wave[len(times)], delta=0.5)
        self.assertAlmostEqual(said[1], wave[len(times) + 1], delta=0.5)
        self.assertIsNone(said[2])

    def test_the_winds_bring_their_haze(self):
        times = [START + i * 300 for i in range(12 * 48)]
        south = lambda i: (i // 72) % 2 == 1  # six hours from the north, six from the south, and so on
        direction = [(t, 180.0 if south(i) else 0.0) for i, t in enumerate(times)]
        haze = [(t, 80.0 if south(i) else 20.0) for i, t in enumerate(times)][::12]  # hourly, as NEA's
        now = times[-1]  # in a southern spell
        said = oracle.foresee_winds(haze, context("outdoor_pm25", wind_direction=direction), now, ahead(now, 24))
        own = [t for t, _ in haze]
        brought = [oracle._interpolate(haze, own, t) for i, t in enumerate(times) if south(i) and own[0] <= t <= own[-1]]
        settle = sum(brought) / len(brought)
        self.assertGreater(settle, 70)  # the south wind brings the haze
        self.assertAlmostEqual(said[-1], settle, delta=0.5)
        self.assertTrue(all(abs(b - settle) <= abs(a - settle) for a, b in zip(said, said[1:])))

    def test_each_weekday_keeps_its_character(self):
        sunday = datetime(2026, 10, 4).timestamp()  # local time, as the week is
        points = [(sunday + h * HOUR, 1000.0 if datetime.fromtimestamp(sunday + h * HOUR).weekday() == 0 else 500.0) for h in range(14 * 24)]
        now = datetime(2026, 10, 18, 22, 0).timestamp()  # a Sunday night
        times = ahead(now, 6, 6)
        said = kabbalah.foresee_week(points, context(), now, times)
        self.assertEqual(said, [1000.0 if datetime.fromtimestamp(t).weekday() == 0 else 500.0 for t in times])

    def test_gematria_spells_the_next_word_and_rests(self):
        points = [(START + i * 60, 900.0 + i) for i in range(91)]  # 1 ppm a minute, up to 990
        now = points[-1][0]
        said = kabbalah.foresee_gematria(points, context(), now, ahead(now, 2))
        self.assertEqual(said[-1], kabbalah.gematria("שבירת הכלים"))  # 1017, the breaking of the vessels
        f = kabbalah.gematria_reading(points)
        self.assertIn("שבירת הכלים", f["prophecy"]["foretold"])

    def test_atbash_mirrors_the_present(self):
        points = [(START + i * 60, 734.0) for i in range(30)]
        self.assertEqual(kabbalah.foresee_temurah(points, context(), points[-1][0], ahead(points[-1][0])), [123] * 24)

    def test_the_moon_speaks_only_after_a_week(self):
        lunar = lambda t: 500 + 300 * astro.moon_illumination(t)
        week = series(lunar, START, START + 8 * DAY, 1800)
        now = week[-1][0]
        times = ahead(now)
        for got, t in zip(oracle.foresee_moon(week, context(), now, times), times):
            self.assertAlmostEqual(got, lunar(t), delta=0.01)
        self.assertIsNone(oracle.foresee_moon(week[-200:], context(), now, times))

    def test_every_seer_says_something_or_nothing(self):
        co2 = series(daily, START, START + 2 * DAY)
        others, regions = household()
        guests = {"co2": co2, **{k: v for k, v in others.items() if k in oracle.GUESTS}}
        now = co2[-1][0]
        times = ahead(now)
        for key, _, _, foresee, targets in prophecy.SEERS:
            for target in targets:
                ctx = context(target, guests, regions=regions, wind_direction=others["outdoor_wind_direction"], placements=PLACED, home=(1.35, 103.85))
                said = foresee(guests[target], ctx, now, times)
                self.assertTrue(said is None or len(said) == len(times), key)
                self.assertTrue(said is None or all(v is None or math.isfinite(v) for v in said), key)


def household(hours=48):
    times = [START + i * 300 for i in range(hours * 12)]
    hourly = times[6::12]
    others = {
        "blueair_pm25": [(t, daily(t, 8, 40, 20)) for t in times],
        "blueair_voc": [(t, 300 + 100 * math.sin(t / 5000)) for t in times],
        "blueair_temperature": [(t, daily(t, 5, 29, 1)) for t in times],
        "outdoor_pm25": [(t, daily(t, 7, 120, 40)) for t in hourly],
        "outdoor_temperature": [(t, daily(t, 6.5, 30, 2)) for t in times],
        "outdoor_humidity": [(t, daily(t, 18.5, 80, 8)) for t in times],
        "outdoor_wind_speed": [(t, 1.5 + math.sin(t / 7000)) for t in times],
        "outdoor_wind_direction": [(t, 225 + 20 * math.sin(t / 3000)) for t in times],
        "outdoor_rain": [(t, 0.0) for t in times],
    }
    regions = {r: [(t, daily(t, 7, 80 + 20 * k, 30)) for t in hourly] for k, r in enumerate(lore.ELEMENTS)}
    regions["central"] = others["outdoor_pm25"]
    return others, regions


def fixed(f):
    """A seer that says ``f(now, t)`` whatever it is shown."""
    return lambda points, ctx, now, times: [f(now, t) for t in times]


class CouncilTest(unittest.TestCase):
    def test_the_council_trusts_the_seer_that_foresaw(self):
        co2 = series(daily, START, START + 2 * DAY)
        seers = (
            ("truth", "Truth", "Test", fixed(lambda now, t: daily(t)), (prophecy.BREATH,)),
            ("liar", "Liar", "Test", fixed(lambda now, t: daily(t) + 300), (prophecy.BREATH,)),
            ("mute", "Mute", "Test", lambda *_: None, (prophecy.BREATH,)),
        )
        with mock.patch.object(prophecy, "SEERS", seers):
            result = prophecy.analyze(co2, co2[0][0], co2[-1][0])
        json.dumps(result, allow_nan=False)
        council = result["councils"][0]
        truth, liar, mute = council["seers"]
        self.assertEqual([s["id"] for s in council["seers"]], ["truth", "liar", "mute"])
        self.assertGreater(truth["weight"], 0.999)
        self.assertAlmostEqual(liar["error"], 300, delta=1)
        self.assertEqual((mute["error"], mute["weight"]), (None, 0.0))
        self.assertGreater(truth["skill"], 0.99)  # far nearer than expecting no change
        for (t, v, lo, hi) in council["forecast"]:
            self.assertAlmostEqual(v, daily(t), delta=1)
            self.assertLessEqual(lo, v)
        self.assertEqual(council["horizon"], 2 * DAY * prophecy.HORIZON_SHARE)
        self.assertIn("Truth", result["prophecy"]["revealed"])

    def test_forecasts_stay_within_what_air_can_be(self):
        co2 = series(daily, START, START + DAY)
        seers = (("wild", "Wild", "Test", fixed(lambda now, t: -5000.0), (prophecy.BREATH,)),)
        with mock.patch.object(prophecy, "SEERS", seers):
            council = prophecy.analyze(co2, co2[0][0], co2[-1][0])["councils"][0]
        self.assertEqual({round(v) for _, v, *_ in council["forecast"]}, {round(oracle.OUTDOOR_CO2 - 25)})

    def test_too_little_to_foresee(self):
        self.assertEqual(prophecy.analyze([], START, START + HOUR)["councils"], [])
        tiny = [(START, 600.0), (START + 60, 610.0)]
        self.assertEqual(prophecy.analyze(tiny, START, START + 60)["councils"], [])

    def airing(self, haze: float, outdoor_pm25: float | None = None):
        """The counsel when the breath, at 900 ppm, climbs 1 ppm a minute, under a haze that stays at ``haze``."""
        co2 = series(lambda t: 900.0, START, START + DAY)
        others = {"outdoor_pm25": series(lambda t: haze, START + 1800, START + DAY, HOUR)} if haze is not None else {}
        seers = (
            ("rise", "Rise", "Test", fixed(lambda now, t: 900 + (t - now) / 60), (prophecy.BREATH,)),
            ("still", "Still", "Test", fixed(lambda now, t: haze), (prophecy.HAZE,)),
        )
        with mock.patch.object(prophecy, "SEERS", seers):
            return prophecy.analyze(co2, START, START + DAY, others=others, outdoor_pm25=outdoor_pm25)

    def test_the_counsel_never_opens_a_window_into_the_haze(self):
        hazy = self.airing(80, 80)
        self.assertIn("1000 ppm at", hazy["prophecy"]["foretold"])
        self.assertIn("Keep the windows sealed", hazy["prophecy"]["counsel"])
        self.assertNotIn("Open a window", json.dumps(hazy))
        clear = self.airing(12, 12)
        self.assertIn("Open a window now", clear["prophecy"]["counsel"])
        unknown = self.airing(None)
        self.assertIn("Open a window", unknown["prophecy"]["counsel"])
        self.assertEqual(unknown["headline"][:8], "1000 ppm")
        self.assertEqual([c["card"] for c in unknown["spread"]][2], "tower")  # the future holds a shattering

    def test_a_unanimous_council_is_suspect(self):
        co2 = series(lambda t: 600.0 + (t - START) / 600, START, START + DAY)
        seers = tuple((f"s{i}", f"Seer {i}", "Test", fixed(lambda now, t, i=i: 600 + (t - START) / 600 + i), (prophecy.BREATH,)) for i in range(3))
        with mock.patch.object(prophecy, "SEERS", seers):
            result = prophecy.analyze(co2, START, START + DAY)
        self.assertIn("Sanhedrin", result["prophecy"]["revealed"])

    def test_the_spread_is_dealt_by_the_numbers(self):
        card = lambda values, hazy=False: prophecy._span_card("Past", values, hazy)["card"]
        self.assertEqual(card([900, 1100]), "tower")
        self.assertEqual(card([1100, 1200]), "hanged")
        self.assertEqual(card([900, 700]), "star")
        self.assertEqual(card([700, 720], hazy=True), "moon")
        self.assertEqual(card([500, 550]), "sun")
        self.assertEqual(card([600, 800]), "chariot")
        self.assertEqual(card([600, 900, 650]), "wheel")
        self.assertEqual(card([700, 710, 705]), "temperance")
        self.assertEqual(card([700, 780]), "strength")
        dealt = prophecy._deal("Future", "tower", "")
        self.assertEqual((dealt["numeral"], dealt["name"]), ("XVI", "The Tower"))

    def test_the_whole_household(self):
        co2 = series(daily, START, START + 2 * DAY)
        others, regions = household()
        result = prophecy.analyze(co2, START, co2[-1][0], others, regions, PLACED, (1.35, 103.85), 117.0)
        json.dumps(result, allow_nan=False)
        self.assertEqual([c["target"] for c in result["councils"]], [prophecy.BREATH, prophecy.HAZE])
        self.assertEqual(len(result["spread"]), 3)
        breath = {s["id"]: s for s in result["councils"][0]["seers"]}
        self.assertEqual(set(breath), {key for key, *_, targets in prophecy.SEERS if prophecy.BREATH in targets})
        self.assertGreater(breath["clock"]["weight"], breath["temurah"]["weight"])  # the daily rhythm beats the mirror
        self.assertAlmostEqual(sum(s["weight"] for s in breath.values()), 1)


class FindingsTest(unittest.TestCase):
    """Every method prophesies, and none of them opens a window into the haze."""

    def test_every_finding_prophesies(self):
        co2 = series(daily, START, START + 2 * DAY, 60)
        temperature = [(t, 21 + v / 1000) for t, v in co2]
        others, regions = household()
        born = {"zytemp": START - DAY, "blueair": START - 2 * DAY}
        found = oracle.analyze(co2, temperature, START, co2[-1][0], others=others, regions=regions, placements=PLACED, born=born, home=(1.35, 103.85))["findings"]
        series_ = {"co2": co2, "temperature": temperature, **{k: v for k, v in others.items() if k in kabbalah.INSTRUMENTS}}
        found += kabbalah.analyze(series_, co2[-1][0])["findings"]
        foretold = 0
        for f in found:
            lines = f.get("prophecy") or {}
            self.assertLessEqual(set(lines), {"foretold", "counsel", "revealed"}, f["id"])
            self.assertTrue(all(isinstance(v, str) and v for v in lines.values()), f["id"])
            foretold += "foretold" in lines
        self.assertGreaterEqual(foretold, len(found) - 2)

    def test_no_prophecy_opens_a_window_into_the_haze(self):
        co2 = series(lambda t: 1500 + 300 * math.sin(t / 7000), START, START + 2 * DAY, 60)  # stuffy throughout
        temperature = [(t, 25.0) for t, _ in co2]
        others, regions = household()
        texts = []
        result = oracle.analyze(co2, temperature, START, co2[-1][0], others=others, regions=regions, placements=PLACED, home=(1.35, 103.85), outdoor_pm25=117)
        texts += [json.dumps(f.get("prophecy", {})) for f in result["findings"]]
        series_ = {"co2": co2, **{k: v for k, v in others.items() if k in kabbalah.INSTRUMENTS}}
        texts += [json.dumps(f.get("prophecy", {})) for f in kabbalah.analyze(series_, co2[-1][0], 117)["findings"]]
        texts.append(json.dumps(prophecy.analyze(co2, START, co2[-1][0], others, regions, PLACED, None, 117)["prophecy"]))
        for text in texts:
            for opening in ("Open a window", "open a window", "Air the room", "air the room", "air it on"):
                self.assertNotIn(opening, text)


class WordsTest(unittest.TestCase):
    def test_when(self):
        now = datetime(2026, 10, 18, 21, 0).timestamp()
        self.assertEqual(oracle._when(now + HOUR, now), "at 22:00")
        self.assertEqual(oracle._when(now + 6 * HOUR, now), "at 03:00 tomorrow")
        self.assertEqual(oracle._when(now + 6 * HOUR, now, "by"), "by 03:00 tomorrow")
        self.assertEqual(oracle._when(now + 4 * DAY, now), "on Oct 22")
        self.assertEqual(oracle._when(now + 4 * DAY, now, "until"), "until Oct 22")

    def test_the_sun_reaches_the_equinox(self):
        # The March equinox of 2026 fell at 14:46 UTC on March 20.
        self.assertLess(abs(astro.sun_reaches(0.0, ts("2026-01-01")) - ts("2026-03-20T14:46")), HOUR)


class RunProphecyTest(unittest.TestCase):
    def test_from_the_database(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "x.sqlite3")
            t0 = time.time() - 30 * HOUR
            readings = []
            for i in range(30 * 12):
                t = t0 + i * 300
                readings += [Reading(t, "co2", 800 + 200 * math.sin(i / 20)), Reading(t, "blueair_pm25", 30 + 10 * math.sin(i / 25))]
                if i % 12 == 6:
                    readings += [Reading(t, nea.PREFIX + r, 100 + 10 * k + 20 * math.sin(i / 40)) for k, r in enumerate(nea.REGIONS)]
            store.add(readings)
            store.place(0, "zytemp", "living room", "table")
            result = server.run_prophecy(store, "24h", "central", (1.35, 103.85))
            self.assertEqual([c["target"] for c in result["councils"]], [prophecy.BREATH, prophecy.HAZE])
            self.assertTrue(result["headline"] and result["prophecy"]["foretold"])
            json.dumps(result, allow_nan=False)
            store.close()


if __name__ == "__main__":
    unittest.main()
