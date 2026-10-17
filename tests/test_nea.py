import datetime as dt
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from aeromancer import nea
from aeromancer.store import Store

SGT = nea.SINGAPORE


def item(hour: dt.datetime, south: float) -> dict:
    """One hourly reading as data.gov.sg serves it (shape observed 2026-10-17)."""
    return {
        "date": hour.date().isoformat(),
        "updatedTimestamp": (hour + dt.timedelta(seconds=35)).isoformat(),
        "timestamp": hour.isoformat(),
        "readings": {"pm25_one_hourly": {"north": 79, "south": south, "west": 187, "east": 116, "central": 135}},
    }


class FakeApi:
    """Hourly readings, newest first per day as the API returns them."""

    def __init__(self, hours: list[dt.datetime]):
        self.hours = hours
        self.asked = []

    def __call__(self, date=None):
        self.asked.append(date)
        if date is None:
            items = [item(self.hours[-1], self.hours[-1].hour)]
        else:
            items = [item(h, h.hour) for h in reversed(self.hours) if h.date() == date]
        return {"code": 0, "data": {"regionMetadata": [], "items": items}, "errorMsg": ""}


class NeaTest(unittest.TestCase):
    def test_parse(self):
        hour = dt.datetime(2026, 10, 17, 20, tzinfo=SGT)
        readings = nea.parse({"code": 0, "data": {"items": [item(hour, 117)]}})
        self.assertEqual(len(readings), 5)
        self.assertIn((hour.timestamp() - 1800, "nea_pm25_south", 117.0), [(r.ts, r.quantity, r.value) for r in readings])
        with self.assertRaises(ValueError):
            nea.parse({"code": 17, "name": "REAL_TIME_API_DATA_NOT_FOUND", "data": None})

    def test_load_region(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "nea.toml"
            self.assertIsNone(nea.load_region(path))
            path.write_text("latitude = 1.35\nlongitude = 103.85\n")
            self.assertIsNone(nea.load_region(path))
            path.write_text('region = "south"\n')
            self.assertEqual(nea.load_region(path), "south")
            path.write_text('region = "Tampines"\n')
            with self.assertRaisesRegex(ValueError, "north, south"):
                nea.load_region(path)

    def test_poll_once_backfills_then_takes_the_latest(self):
        start = dt.datetime(2026, 10, 15, 22, tzinfo=SGT)
        api = FakeApi([start + dt.timedelta(hours=h) for h in range(30)])  # to 10-17 03:00
        now = api.hours[-1].timestamp() + 60
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "x.sqlite3")
            self.addCleanup(store.close)

            # First poll: whole days, from a week back (clipped to what exists) to today.
            since = nea.poll_once(store, 0.0, now=now, get=api, pause=0)
            self.assertEqual(since, api.hours[-1].timestamp() - 1800)
            self.assertEqual(api.asked[0], dt.date(2026, 10, 10))
            self.assertEqual(api.asked[-1], dt.date(2026, 10, 17))
            south = store.series("nea_pm25_south", 0, now, 1)
            self.assertEqual([v for _, v, _, _ in south], [h.hour for h in api.hours])
            self.assertEqual(store.count(), 30 * 5)

            # Nothing new: one request, nothing stored.
            api.asked.clear()
            self.assertEqual(nea.poll_once(store, since, now=now + 600, get=api, pause=0), since)
            self.assertEqual((api.asked, store.count()), ([None], 30 * 5))

            # The next hour: stored from the latest reading.
            api.hours.append(api.hours[-1] + dt.timedelta(hours=1))
            since = nea.poll_once(store, since, now=api.hours[-1].timestamp() + 60, get=api, pause=0)
            self.assertEqual((since, api.asked[-1], store.count()), (api.hours[-1].timestamp() - 1800, None, 31 * 5))

            # Three hours missed: today's readings fill them in.
            api.hours += [api.hours[-1] + dt.timedelta(hours=k) for k in (1, 2, 3)]
            api.asked.clear()
            since = nea.poll_once(store, since, now=api.hours[-1].timestamp() + 60, get=api, pause=0)
            self.assertEqual((since, api.asked, store.count()), (api.hours[-1].timestamp() - 1800, [dt.date(2026, 10, 17)], 34 * 5))

    def test_failed_backfill_keeps_the_days_before(self):
        api = FakeApi([dt.datetime(2026, 10, 15, 22, tzinfo=SGT) + dt.timedelta(hours=h) for h in range(30)])
        now = api.hours[-1].timestamp() + 60

        def limited(date=None):
            if date == dt.date(2026, 10, 17):
                raise ConnectionError("HTTP Error 429: Too Many Requests")
            return api(date)

        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "x.sqlite3")
            self.addCleanup(store.close)
            with self.assertRaises(ConnectionError):
                nea.poll_once(store, 0.0, now=now, get=limited, pause=0)
            self.assertEqual(store.count(), 26 * 5)  # 10-15 22:00 to 10-16 23:00
            nea.poll_once(store, store.last_ts("nea_pm25_*"), now=now, get=api, pause=0)
            self.assertEqual(store.count(), 30 * 5)

    def test_restamp_hour_ends(self):
        hour = dt.datetime(2026, 10, 17, 20, tzinfo=SGT).timestamp()
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "x.sqlite3")
            self.addCleanup(store.close)
            store.add(nea.parse({"code": 0, "data": {"items": [item(dt.datetime(2026, 10, 17, 19, tzinfo=SGT), 156)]}}))
            store.db.execute("INSERT INTO readings VALUES (?, 'nea_pm25_south', 117), (?, 'blueair_pm25', 40)", (hour, hour))
            nea.restamp_hour_ends(store)
            nea.restamp_hour_ends(store)  # idempotent
            self.assertEqual(store.series("nea_pm25_south", 0, hour, 1), [(hour - 5400, 156, 156, 156), (hour - 1800, 117, 117, 117)])
            self.assertEqual(store.last_ts("blueair_*"), hour)

    def test_poll_retries_after_failure(self):
        stop = threading.Event()
        hour = dt.datetime(2026, 10, 17, 20, tzinfo=SGT)
        calls = []

        def flaky(date=None):
            calls.append(date)
            if len(calls) == 1:
                raise ConnectionError("network down")
            stop.set()
            return {"code": 0, "data": {"items": [item(hour, 117)] if date == hour.date() else []}}

        with tempfile.TemporaryDirectory() as d, mock.patch.object(nea, "fetch", flaky), \
                mock.patch.object(nea, "POLL_SECONDS", 0), mock.patch.object(nea, "BACKFILL_PAUSE", 0), mock.patch("time.time", return_value=hour.timestamp() + 60), \
                self.assertLogs("aeromancer.nea", "WARNING"):
            nea.poll(Path(d) / "x.sqlite3", stop=stop)
            store = Store(Path(d) / "x.sqlite3")
            self.addCleanup(store.close)
            self.assertEqual(store.count(), 5)


if __name__ == "__main__":
    unittest.main()
