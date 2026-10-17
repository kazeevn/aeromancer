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


if __name__ == "__main__":
    unittest.main()
