import math
import tempfile
import unittest
from pathlib import Path

from aeromancer import filter_health as fh
from aeromancer.device import Reading
from aeromancer.store import Store

DAY = 86400.0
REPLACED = 1_700_000_000.0
TEST = REPLACED + 30 * DAY


def uploads(start, count, fan, auto, pm, step=300.0):
    """Readings as the poller stores them: PM2.5 and the settings at each upload."""
    out = []
    for i in range(count):
        ts = start + i * step
        out += [
            Reading(ts, fh.PM, float(pm(i * step / 3600))),
            Reading(ts, fh.FAN, float(fan)),
            Reading(ts, fh.AUTO, float(auto)),
        ]
    return out


def decay(rate, steady=2.5, amp=60.0):
    return lambda hours: round(steady + amp * math.exp(-rate * hours))


class FilterHealthTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.dir.name) / "db.sqlite3")
        self.store.add([Reading(REPLACED, fh.REPLACED, 1.0)])

    def tearDown(self):
        self.store.close()
        self.dir.cleanup()

    def add_test(self, start, rate, fill=6, minutes=60):
        self.store.add(uploads(start - 3600, 12, 3, 1, lambda h: 30))  # auto before
        self.store.add(uploads(start - fill * 300, fill, 0, 0, lambda h: 5 + 8 * h * 12))  # fan off, window open
        self.store.add(uploads(start, minutes // 5, 1, 0, decay(rate)))
        self.store.add(uploads(start + minutes * 60, 6, 1, 1, lambda h: 3))  # back to auto

    def test_app_days_left(self):
        self.assertEqual(fh.app_days_left(0), 180)
        self.assertEqual(fh.app_days_left(8200), 152)
        self.assertEqual(fh.app_days_left(52000), 0)

    def test_fit_decay_recovers_the_rate(self):
        points = [(i * 300.0, 2.0 + 50 * math.exp(-3.0 * i / 12)) for i in range(10)]
        rate, error, steady = fh.fit_decay(points)
        self.assertAlmostEqual(rate, 3.0, places=4)
        self.assertLess(error, 1e-3)
        self.assertAlmostEqual(steady, 2.0, places=3)
        self.assertIsNone(fh.fit_decay([(i * 300.0, 10.0 + i) for i in range(10)]))  # rising: no decay

    def test_finds_a_test_after_the_fan_was_off(self):
        self.add_test(TEST, 4.5)
        tests = fh.find_tests(self.store, REPLACED, TEST + DAY)
        self.assertEqual(len(tests), 1)
        self.assertEqual(tests[0].start, TEST)
        self.assertEqual(tests[0].points, 10)  # the first two uploads are the room mixing
        self.assertAlmostEqual(tests[0].rate, 4.5, delta=0.3)

    def test_ignores_speed_1_without_the_fan_off_before(self):
        self.store.add(uploads(TEST - 3600, 12, 3, 1, lambda h: 30))
        self.store.add(uploads(TEST, 12, 1, 0, decay(4.5)))  # set by hand, as in a constant-speed regime
        self.assertEqual(fh.find_tests(self.store, REPLACED, TEST + DAY), [])

    def test_ignores_short_runs_and_small_drops(self):
        self.add_test(TEST, 4.5, minutes=30)
        self.add_test(TEST + DAY, 0.2)
        self.assertEqual(fh.find_tests(self.store, REPLACED, TEST + 2 * DAY), [])

    def test_health_and_its_spread(self):
        settings = fh.Settings(room_volume=20.0, cadr=100.0)
        h, sd = fh.health(4.65, 0.2, settings)
        self.assertAlmostEqual(h, (4.65 - 0.65) * 20 / 100)
        self.assertAlmostEqual(sd, math.hypot(math.hypot(0.2, 0.7 / math.sqrt(12)) / 4.0, 0.15 / math.sqrt(3)))
        self.assertEqual(fh.health(0.5, 0.1, settings)[0], 0.0)

    def test_forecast_by_age(self):
        settings = fh.Settings(room_volume=20.0, cadr=100.0)
        now = TEST + DAY
        f = fh.forecast([(TEST, 0.8, 0.2)], REPLACED, now, settings)["age"]
        tau = 30 / -math.log(0.8)
        self.assertAlmostEqual(f["scale"], tau)
        self.assertAlmostEqual(f["now"], math.exp(-31 / tau))
        self.assertAlmostEqual(f["due"], REPLACED + tau * math.log(2) * DAY)
        self.assertLess(f["due_early"], f["due"])
        self.assertIsNone(f["due_late"])  # 0.8 within a factor of exp(±0.33) allows no wear at all
        f = fh.forecast([(TEST, 0.8, 0.01)], REPLACED, now, settings)["age"]
        self.assertLess(f["due"], f["due_late"])
        self.assertNotIn("caught", fh.forecast([(TEST, 0.8, 0.01)], REPLACED, now, settings))

    def test_forecast_by_what_it_caught_goes_at_the_last_weeks_pace(self):
        settings = fh.Settings(room_volume=20.0, cadr=100.0)
        now = TEST + DAY
        # 100 mg a day for the first 24 days, then 400.
        series = [(REPLACED + d * DAY, 100.0 * min(d, 24) + 400.0 * max(0, d - 24)) for d in range(32)]
        f = fh.forecast([(TEST, 0.8, 0.01)], REPLACED, now, settings, series)
        mg_at_test = 100 * 24 + 400 * 6
        m0 = mg_at_test / -math.log(0.8)
        self.assertAlmostEqual(f["caught"]["scale"], m0)
        self.assertAlmostEqual(f["caught_mg_per_day"], 400.0)
        self.assertAlmostEqual(f["caught"]["due"], now + (m0 * math.log(2) - series[-1][1]) / 400 * DAY)
        self.assertLess(f["caught"]["due"], f["age"]["due"])  # caught faster lately

    def test_caught(self):
        settings = fh.Settings(room_volume=20.0, cadr=80.0, airflow=(100.0, 200.0, 400.0))
        start = TEST
        self.store.add(uploads(start, 4, 1, 1, lambda h: 10))  # speed 1: 80 m³/h of clean air
        self.store.add(uploads(start + 1200, 4, 3, 1, lambda h: 10))  # speed 3: 320 m³/h
        self.store.add([Reading(start + 2400, fh.PM, 40.0), Reading(start + 2700, fh.PM, 40.0)])  # no speed: kept
        self.store.add([Reading(start + 9000, fh.PM, 40.0), Reading(start + 9300, fh.PM, 20.0)])  # after a gap: auto's speeds
        self.store.add(uploads(start + 9600, 2, 0, 0, lambda h: 40))  # fan off catches nothing
        mg = dict(fh.caught(self.store, start, start + DAY, settings))
        self.assertAlmostEqual(mg[start + 1200], 10 * 80 * 4 * 300 / 3600 / 1000)
        self.assertAlmostEqual(mg[start + 2400] - mg[start + 1200], 10 * 320 * 4 * 300 / 3600 / 1000)
        self.assertAlmostEqual(mg[start + 2700] - mg[start + 2400], 40 * 320 * 300 / 3600 / 1000)
        self.assertAlmostEqual(mg[start + 9000] - mg[start + 2700], 40 * 320 * 600 / 3600 / 1000)  # gap capped
        self.assertAlmostEqual(mg[start + 9300] - mg[start + 9000], 40 * 320 * 300 / 3600 / 1000)  # 40: speed 3
        self.assertAlmostEqual(mg[start + 9600] - mg[start + 9300], 20 * 80 * 300 / 3600 / 1000)  # 20: speed 1
        self.assertAlmostEqual(mg[start + 9900], mg[start + 9600])

    def test_status(self):
        self.store.add([Reading(TEST + DAY, fh.blueair.FILTER_COUNTER, 8200.0), Reading(TEST + DAY, fh.EXPIRED, 0.0)])
        self.add_test(TEST, 4.5)
        bare = fh.status(self.store, None, now=TEST + DAY)
        self.assertEqual((bare["replaced"], bare["app_days_left"], bare["expired"]), (REPLACED, 152, False))
        self.assertNotIn("health", bare["tests"][0])
        self.assertIsNone(bare["forecast"])
        full = fh.status(self.store, fh.Settings(20.0, 100.0), now=TEST + DAY)
        test = full["tests"][0]
        self.assertLess(test["health_low"], test["health"], test["health_high"])
        self.assertAlmostEqual(test["health"], (test["rate"] - 0.65) * 0.2)
        self.assertGreater(full["forecast"]["age"]["due"], TEST)
        self.assertNotIn("caught", full["forecast"])
        with_airflow = fh.status(self.store, fh.Settings(20.0, 100.0, airflow=(125.0, 250.0, 500.0)), now=TEST + DAY)
        self.assertGreater(with_airflow["forecast"]["caught"]["due"], TEST)

    def test_load_settings(self):
        path = Path(self.dir.name) / "blueair.toml"
        self.assertIsNone(fh.load_settings(path))
        path.write_text('username = "me@example.com"\npassword = "pw"\n')
        self.assertIsNone(fh.load_settings(path))
        path.write_text(path.read_text() + "[filter]\nroom_volume = 30\ncadr = 100\nbackground = [0.2, 0.8]\nairflow = [125, 500]\n")
        self.assertEqual(fh.load_settings(path), fh.Settings(30.0, 100.0, background=(0.2, 0.8), airflow=(125.0, 500.0)))
        path.write_text("[filter]\nroom_volume = 30\n")
        with self.assertRaises(ValueError):
            fh.load_settings(path)
        path.write_text('[filter]\nroom_volume = 30\ncadr = "lots"\n')
        with self.assertRaises(ValueError):
            fh.load_settings(path)


if __name__ == "__main__":
    unittest.main()
