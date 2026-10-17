import unittest
from datetime import datetime, timezone

from aeromancer import astro


def ts(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


class MercuryTest(unittest.TestCase):
    def test_retrograde_periods_2024(self):
        # Published stations (UTC): Apr 1 - Apr 25, Aug 5 - Aug 28, Nov 26 - Dec 15.
        expected = [("2024-04-01", "2024-04-25"), ("2024-08-05", "2024-08-28"), ("2024-11-26", "2024-12-15")]
        got = astro.mercury_retrograde_intervals(ts("2024-02-01"), ts("2024-12-31"))
        self.assertEqual(len(got), 3)
        for (a, b), (ea, eb) in zip(got, expected):
            self.assertLess(abs(a - ts(ea)), 86400)
            self.assertLess(abs(b - ts(eb)), 86400)

    def test_next_station(self):
        station, turn = astro.next_mercury_station(ts("2026-10-17"))
        self.assertEqual(turn, "retrograde")
        self.assertLess(abs(station - ts("2026-10-24")), 86400)


class MoonTest(unittest.TestCase):
    def test_full_moon(self):
        # Full moon 2024-04-23 23:49 UTC.
        self.assertGreater(astro.moon_illumination(ts("2024-04-23T23:49")), 0.98)
        self.assertEqual(astro.moon_phase_name(ts("2024-04-23T23:49")), "Full Moon")

    def test_lunations_alternate(self):
        events = astro.lunations(ts("2024-01-01"), ts("2024-03-01"))
        kinds = [k for _, k in events]
        self.assertEqual(len(events), 4)
        self.assertTrue(all(a != b for a, b in zip(kinds, kinds[1:])))


class SunTest(unittest.TestCase):
    def test_sun_signs(self):
        self.assertEqual(astro.zodiac_sign(astro.sun_longitude(ts("2026-10-17")))[0], "Libra")
        self.assertEqual(astro.zodiac_sign(astro.sun_longitude(ts("2026-07-01")))[0], "Cancer")

    def test_equation_of_time(self):
        # Published extremes: about -14.2 min on Feb 11 and +16.4 min on Nov 3.
        self.assertAlmostEqual(astro.equation_of_time(ts("2026-02-11T12:00")), -14.2, delta=0.5)
        self.assertAlmostEqual(astro.equation_of_time(ts("2026-11-03T12:00")), 16.4, delta=0.5)

    def test_solar_time_and_height(self):
        # Near the equinox the Sun is overhead at the equator at solar noon.
        noon = ts("2026-03-20T12:00") - astro.equation_of_time(ts("2026-03-20T12:00")) * 60
        self.assertAlmostEqual(astro.solar_hours(noon, 0.0), 12, delta=0.01)
        self.assertGreater(astro.sun_elevation(noon, 0.0, 0.0), 89)
        self.assertAlmostEqual(astro.solar_hours(noon, 90.0), 18, delta=0.01)
        self.assertAlmostEqual(astro.half_day_hours(noon, 1.35), 6.055, delta=0.01)  # refraction lengthens the day

    def test_planetary_hours(self):
        hours = astro.planetary_hours(ts("2026-10-17T06:00"), 1.35, 103.85)  # 14:00 in Singapore, a Saturday
        self.assertEqual(len(hours), 24)
        self.assertEqual(hours[0][2], "Saturn")
        self.assertEqual([h[2] for h in hours[:8]], ["Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury", "Moon", "Saturn"])
        for (_, end, _), (start, _, _) in zip(hours, hours[1:]):
            self.assertAlmostEqual(end, start)
        self.assertAlmostEqual(hours[-1][1] - hours[0][0], astro.DAY)
        self.assertTrue(hours[0][0] <= ts("2026-10-17T06:00") < hours[-1][1])


class MercuryShadowTest(unittest.TestCase):
    def test_shadows_2024(self):
        # Published: shadow from Jul 17, retrograde Aug 5 - Aug 28, shadow until Sep 11.
        start, retro, direct, end = astro.mercury_cycle(ts("2024-07-20"))
        for got, expected in ((start, "2024-07-17"), (retro, "2024-08-05"), (direct, "2024-08-28"), (end, "2024-09-11")):
            self.assertLess(abs(got - ts(expected)), 86400)
        self.assertEqual(astro.mercury_shadow(ts("2024-07-20"))[0], "pre")
        self.assertIsNone(astro.mercury_shadow(ts("2024-08-10")))  # retrograde, not in shadow
        self.assertEqual(astro.mercury_shadow(ts("2024-09-01"))[0], "post")
        self.assertIsNone(astro.mercury_shadow(ts("2024-09-20")))
        self.assertEqual(astro.mercury_cycle(ts("2024-09-20"))[1] // 86400, astro.next_mercury_station(ts("2024-09-20"))[0] // 86400)


class CalendarTest(unittest.TestCase):
    def test_chinese_new_year(self):
        for year, day in ((2024, "2024-02-10"), (2025, "2025-01-29"), (2026, "2026-02-17"), (2027, "2027-02-06")):
            self.assertEqual(astro.chinese_new_year(year), ts(day) - 8 * 3600)  # midnight in China


if __name__ == "__main__":
    unittest.main()
