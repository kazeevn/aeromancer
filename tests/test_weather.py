import datetime as dt
import tempfile
import unittest
from pathlib import Path

from aeromancer import weather
from aeromancer.store import Store

SGT = weather.nea.SINGAPORE
HOME = (1.35, 103.85)
# id -> (latitude, longitude); S1-S3 are the nearest to HOME, S4 is far
STATIONS = {"S1": (1.351, 103.85), "S2": (1.36, 103.85), "S3": (1.35, 103.87), "S4": (1.25, 103.65)}
TEMPERATURE, RAIN, WIND = weather.KINDS[0], weather.KINDS[2], weather.KINDS[3]


class FakeApi:
    """Readings every ``step`` seconds up to ``self.until``, paged 25 at a time, newest first per day (shape observed 2026-10-17)."""

    def __init__(self, kind, step: int, until: dt.datetime, unit=None):
        self.kind, self.step, self.until, self.unit = kind, step, until, unit or kind.unit
        self.asked = []
        self.missing = set()  # (timestamp, station) not reported yet

    def value(self, t: dt.datetime, station: str) -> float:
        return t.hour * 100 + t.minute + int(station[1:]) / 10

    def __call__(self, kind, date, token=None):
        self.asked.append((date, token))
        start = dt.datetime.combine(date, dt.time(), SGT)
        end = min(self.until, start + dt.timedelta(days=1) - dt.timedelta(seconds=self.step))
        times = []
        while end >= start:
            times.append(end)
            end -= dt.timedelta(seconds=self.step)
        offset = int(token or 0)
        page = times[offset : offset + 25]
        if not times:
            return {"code": 0, "data": {"readings": []}}  # what fetch makes of a 404
        stations = [{"id": i, "deviceId": i, "name": f"Station {i}", "location": {"latitude": la, "longitude": lo}} for i, (la, lo) in STATIONS.items()]
        readings = [
            {"timestamp": t.isoformat(), "data": [{"stationId": i, "value": self.value(t, i)} for i in STATIONS if (t, i) not in self.missing]}
            for t in page
        ]
        return {
            "code": 0,
            "data": {"stations": stations, "readings": readings, "readingType": "x", "readingUnit": self.unit, "paginationToken": str(offset + 25)},
            "errorMsg": "",
        }


class WeatherTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.store = Store(Path(d.name) / "x.sqlite3")
        self.addCleanup(self.store.close)

    def test_load_home(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "nea.toml"
            self.assertIsNone(weather.load_home(path))
            path.write_text('region = "central"\n')
            self.assertIsNone(weather.load_home(path))
            path.write_text('region = "central"\nlatitude = 1.35\nlongitude = 103.85\n')
            self.assertEqual(weather.load_home(path), HOME)
            path.write_text("latitude = 103.85\nlongitude = 1.35\n")
            with self.assertRaisesRegex(ValueError, "in Singapore"):
                weather.load_home(path)

    def test_backfills_a_day_then_takes_the_latest(self):
        until = dt.datetime(2026, 10, 17, 1, 3, tzinfo=SGT)
        api = FakeApi(TEMPERATURE, 60, until)
        now = until.timestamp() + 60
        n = weather.poll_kind(self.store, TEMPERATURE, HOME, now=now, get=api, pause=0)
        # From a day back, one point per 5 minutes, from the three nearest stations only.
        self.assertEqual(n, 3 * 24 * 12)
        self.assertEqual({d for d, _ in api.asked}, {dt.date(2026, 10, 16), dt.date(2026, 10, 17)})
        s1 = self.store.series("nea_temperature_S1", 0, now, 1)
        self.assertEqual(s1[-1][:2], (dt.datetime(2026, 10, 17, 1, 0, tzinfo=SGT).timestamp(), 100.1))
        self.assertEqual(s1[0][0], dt.datetime(2026, 10, 16, 1, 5, tzinfo=SGT).timestamp())
        self.assertEqual(self.store.series("nea_temperature_S4", 0, now, 1), [])
        self.assertEqual(set(self.store.stations()), {"S1", "S2", "S3"})

        # A poll later: one page, one new point per station.
        api.until += dt.timedelta(minutes=5)
        api.asked.clear()
        self.assertEqual(weather.poll_kind(self.store, TEMPERATURE, HOME, now=now + 300, get=api, pause=0), 3)
        self.assertEqual(api.asked, [(dt.date(2026, 10, 17), None)])
        self.assertEqual(weather.poll_kind(self.store, TEMPERATURE, HOME, now=now + 300, get=api, pause=0), 0)

    def test_late_station_is_filled_in(self):
        until = dt.datetime(2026, 10, 17, 21, 15, tzinfo=SGT)
        api = FakeApi(RAIN, 300, until)
        api.missing = {(until, "S2"), (until, "S3")}
        weather.poll_kind(self.store, RAIN, HOME, now=until.timestamp() + 60, get=api, pause=0)
        mid = until.timestamp() - 150  # 5-minute totals stamped mid-window
        self.assertEqual(self.store.last_ts("nea_rain_S1"), mid)
        self.assertEqual(self.store.last_ts("nea_rain_S2"), mid - 300)
        api.missing.clear()
        self.assertEqual(weather.poll_kind(self.store, RAIN, HOME, now=until.timestamp() + 360, get=api, pause=0), 2)
        self.assertEqual(self.store.last_ts("nea_rain_S2"), mid)

    def test_just_after_midnight_uses_yesterday(self):
        api = FakeApi(WIND, 60, dt.datetime(2026, 10, 16, 23, 59, tzinfo=SGT))
        now = dt.datetime(2026, 10, 17, 0, 0, 30, tzinfo=SGT).timestamp()
        weather.poll_kind(self.store, WIND, HOME, now=now, get=api, pause=0)
        rows = self.store.series("nea_wind_speed_S1", 0, now, 1)
        # Knots to m/s, stamped in the middle of the 10-minute average ending 23:55.
        self.assertEqual(rows[-1][0], dt.datetime(2026, 10, 16, 23, 50, tzinfo=SGT).timestamp())
        self.assertAlmostEqual(rows[-1][1], 2355.1 * 1852 / 3600)

    def test_unit_change_is_an_error(self):
        api = FakeApi(TEMPERATURE, 60, dt.datetime(2026, 10, 17, 1, tzinfo=SGT), unit="deg F")
        with self.assertRaisesRegex(ValueError, "deg F"):
            weather.poll_kind(self.store, TEMPERATURE, HOME, now=api.until.timestamp(), get=api, pause=0)

    def test_nearest(self):
        stations = [{"id": i, "location": {"latitude": la, "longitude": lo}} for i, (la, lo) in STATIONS.items()]
        self.assertEqual([s["id"] for s in weather.nearest(stations, HOME)], ["S1", "S2", "S3"])
        self.assertAlmostEqual(weather.distance(HOME, (1.36, 103.85)), 1.112, places=3)


if __name__ == "__main__":
    unittest.main()
