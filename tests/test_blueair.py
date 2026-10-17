import asyncio
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock
from pathlib import Path

from aeromancer import blueair
from aeromancer.store import Store


class FakeApi:
    """Answers like Blueair's legacy cloud, as observed from a 490i.

    ``uploads`` are ``[time, pm, tmp, hum, voc, allpollu]`` rows, oldest first.
    """

    def __init__(self, uploads):
        self.uploads = uploads
        self.asked = []

    async def get_data_points_since(self, uuid, seconds_ago, sample_period):
        self.asked.append(seconds_ago)
        latest = self.uploads[-1]
        rows = []
        # Buckets on a grid ending at the latest upload, stamped with their start;
        # the one stamped with the latest upload holds just that upload.
        for k in range(seconds_ago // sample_period):
            start = latest[0] - seconds_ago + k * sample_period
            inside = [u for u in self.uploads if start < u[0] <= start + sample_period]
            if inside:
                rows.append([start] + [sum(col) / len(inside) for col in list(zip(*inside))[1:]])
        rows.append(latest)
        return {"uuid": uuid, "sensors": ["time", "pm", "tmp", "hum", "voc", "allpollu"], "datapoints": rows}

    async def get_attributes(self, uuid):
        return {"fan_speed": "2", "mode": "auto"}


class BlueairTest(unittest.TestCase):
    def test_parse_datapoints(self):
        readings = blueair.parse_datapoints(
            {"sensors": ["time", "pm", "tmp", "newthing"], "datapoints": [[100, 3, 21.5, None], [400, 4, 21.0, 7]]}
        )
        self.assertEqual(
            [(r.ts, r.quantity, r.value) for r in readings],
            [
                (100, "blueair_pm25", 3),
                (100, "blueair_temperature", 21.5),
                (400, "blueair_pm25", 4),
                (400, "blueair_temperature", 21.0),
                (400, "blueair_newthing", 7),
            ],
        )
        with self.assertRaises(ValueError):
            blueair.parse_datapoints({"error": "token expired"})

    def test_load_config(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "blueair.toml"
            self.assertIsNone(blueair.load_config(path))
            path.write_text('username = "me@example.com"\npassword = "p\\"w"\n')
            path.chmod(0o600)
            self.assertEqual(blueair.load_config(path), blueair.Config("me@example.com", 'p"w'))
            path.write_text(path.read_text() + 'device = "Kent"\n')
            path.chmod(0o644)
            with self.assertLogs("aeromancer.blueair", "WARNING"):
                self.assertEqual(blueair.load_config(path).device, "Kent")
            path.chmod(0o600)
            path.write_text('username = "me@example.com"\n')
            with self.assertRaisesRegex(ValueError, "password"):
                blueair.load_config(path)

    def test_pick(self):
        devices = [{"uuid": "A1", "name": "Bedroom"}, {"uuid": "B2", "name": "Office"}]
        self.assertEqual(blueair.pick(devices, None), ("A1", "Bedroom"))
        self.assertEqual(blueair.pick(devices, "Office"), ("B2", "Office"))
        self.assertEqual(blueair.pick(devices, "B2"), ("B2", "Office"))
        with self.assertRaises(LookupError):
            blueair.pick(devices, "Kitchen")
        with self.assertRaises(LookupError):
            blueair.pick([], None)

    def test_poll_once_stores_uploads_at_their_times(self):
        now = time.time()
        # Uploads every 305 s, as the 490i does.
        api = FakeApi([[now - 305 * (9 - i), i, 21.0, 40, 100, 5] for i in range(10)])
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "x.sqlite3")
            self.addCleanup(store.close)

            # First poll: the latest upload, plus a day of averages restamped to their buckets' ends.
            since = asyncio.run(blueair.poll_once(api, "A1", store, 0.0))
            self.assertEqual(api.asked, [0, blueair.MAX_BACKFILL])
            self.assertEqual(since, now)
            pm = store.series("blueair_pm25", 0, now, 1)
            self.assertEqual(pm[-1][:2], (now, 9))
            self.assertEqual([round(v) for _, v, _, _ in pm[:-1]], list(range(9)))
            for (ts, *_), upload in zip(pm, api.uploads):
                self.assertLessEqual(abs(ts - upload[0]), blueair.SAMPLE_PERIOD)
            self.assertEqual(store.series("blueair_fan_speed", 0, now, 1), [(now, 2.0, 2.0, 2.0)])
            count = store.count()

            # Nothing new: one cheap request, nothing stored.
            self.assertEqual(asyncio.run(blueair.poll_once(api, "A1", store, since)), since)
            self.assertEqual(api.asked[-1], 0)
            self.assertEqual(store.count(), count)

            # One new upload: stored as is, at its own time.
            api.uploads.append([now + 305, 42, 21.0, 40, 100, 5])
            since = asyncio.run(blueair.poll_once(api, "A1", store, since))
            self.assertEqual((since, api.asked[-1]), (now + 305, 0))
            self.assertEqual(store.series("blueair_pm25", now + 1, now + 305, 1), [(now + 305, 42, 42, 42)])
            self.assertEqual(store.count(), count + 6)

            # Two uploads missed: the latest as is, the missed one from the averages.
            api.uploads += [[now + 610, 50, 21.0, 40, 100, 5], [now + 915, 60, 21.0, 40, 100, 5], [now + 1220, 70, 21.0, 40, 100, 5]]
            self.assertEqual(asyncio.run(blueair.poll_once(api, "A1", store, since)), now + 1220)
            pm = store.series("blueair_pm25", now + 306, now + 1220, 1)
            self.assertEqual([v for _, v, _, _ in pm], [50, 60, 70])
            self.assertEqual(store.latest(), {})  # the meter's quantities stay the meter's

    def test_poll_logs_in_again_after_failure(self):
        stop = threading.Event()
        sessions = []

        class FakeHttpBlueair(FakeApi):
            def __init__(self, username, password):
                super().__init__([[time.time() - 60, 3, 21.0, 40, 100, 5]])
                self.closed = False
                sessions.append(self)

            async def get_devices(self):
                if len(sessions) == 1:
                    raise ConnectionError("cloud down")
                return [{"uuid": "A1", "name": "Bedroom"}]

            async def get_attributes(self, uuid):
                stop.set()
                return await super().get_attributes(uuid)

            async def cleanup_client_session(self):
                self.closed = True

        fake = types.ModuleType("blueair_api")
        fake.HttpBlueair = FakeHttpBlueair
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(sys.modules, blueair_api=fake), \
                mock.patch.object(blueair, "POLL_SECONDS", 0), self.assertLogs("aeromancer.blueair", "WARNING"):
            blueair.poll(Path(d) / "x.sqlite3", blueair.Config("user", "pass"), stop=stop)
            store = Store(Path(d) / "x.sqlite3")
            self.addCleanup(store.close)
            self.assertEqual(store.count(), 6)
        self.assertEqual([s.closed for s in sessions], [True, True])


if __name__ == "__main__":
    unittest.main()
