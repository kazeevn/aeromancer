import datetime as dt
import json
import re
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from aeromancer import health
from aeromancer.store import Store

NOW = dt.datetime(2026, 10, 18, 10, tzinfo=dt.timezone.utc).timestamp()
FITBIT = {"recordingMethod": "PASSIVELY_MEASURED", "device": {"displayName": "Fitbit"}, "platform": "FITBIT"}
PHONE = {"recordingMethod": "PASSIVELY_MEASURED", "device": {"displayName": "MobileTrack"}, "platform": "FITBIT"}


def utc(ts):
    return health._rfc3339(ts)


def heart_rate(ts, bpm):  # shapes as the API sent them on 2026-10-18
    return {"dataSource": FITBIT, "heartRate": {"sampleTime": {"physicalTime": utc(ts), "utcOffset": "28800s"}, "beatsPerMinute": str(bpm)}}


def steps(ts, count, source=FITBIT):
    interval = {"startTime": utc(ts), "startUtcOffset": "28800s", "endTime": utc(ts + 60), "endUtcOffset": "28800s"}
    return {"dataSource": source, "steps": {"interval": interval, "count": str(count)}}


def stage(start, end, kind):
    return {"startTime": utc(start), "startUtcOffset": "28800s", "endTime": utc(end), "endUtcOffset": "28800s", "type": kind}


def sleep(start, stages, end):
    return {
        "dataSource": FITBIT,
        "sleep": {
            "interval": {"startTime": utc(start), "startUtcOffset": "28800s", "endTime": utc(end), "endUtcOffset": "28800s"},
            "type": "STAGES",
            "stages": stages,
            "shortAwakenings": [stage(start + 600, start + 660, "AWAKE")],
            "metadata": {"stagesStatus": "SUCCEEDED", "processed": True, "mainSleep": True},
        },
    }


def _when(data_type, point):
    """The time a filter goes by: a sample's, an interval's start, a sleep's end; None for the daily types."""
    inner = next(v for k, v in point.items() if k != "dataSource")
    if "sampleTime" in inner:
        return inner["sampleTime"]["physicalTime"]
    if "interval" in inner:
        return inner["interval"]["endTime" if data_type == "sleep" else "startTime"]
    return None


class FakeSession:
    """Serves ``points[data_type]`` newest first, ``page`` at a time, as the API does; records the filters asked.

    Like the API, it keeps the points from the filter's ``>=`` time and before its ``<`` one, to the second.
    """

    def __init__(self, points, page=2):
        self.points, self.page, self.asked = points, page, []

    def get(self, url):
        parts = urllib.parse.urlsplit(url)
        data_type = parts.path.split("/")[-2]
        query = dict(urllib.parse.parse_qsl(parts.query))
        self.asked.append((data_type, query["filter"]))
        start = int(query.get("pageToken", 0))
        after, before = re.search(r'>= "([^"]+)"', query["filter"]), re.search(r'< "([^"]+)"', query["filter"])
        matching = [
            p for p in self.points.get(data_type, [])
            if (when := _when(data_type, p)) is None
            or ((not after or when >= after[1]) and (not before or when < before[1]))  # RFC 3339 in UTC sorts as text
        ]
        points = matching[start : start + self.page]
        more = start + self.page < len(matching)
        return {"dataPoints": points, **({"nextPageToken": str(start + self.page)} if more else {})}


class SleepTest(unittest.TestCase):
    def test_stages_become_codes_and_the_end_zero(self):
        t = NOW - 8 * 3600
        s = sleep(t, [stage(t + 300, t + 3600, "LIGHT"), stage(t, t + 300, "AWAKE"), stage(t + 3600, t + 7200, "DEEP")], t + 7200)
        got = [(r.ts - t, r.value) for r in health.sleep_readings(s["sleep"])]
        self.assertEqual(got, [(0, 1), (300, 3), (3600, 4), (7200, 0)])  # short awakenings are not stored

    def test_out_of_bed_is_zero_until_back_in_the_stage_then(self):
        t = NOW - 8 * 3600
        s = sleep(t, [stage(t, t + 3600, "LIGHT"), stage(t + 3600, t + 7200, "REM")], t + 7200)["sleep"]
        s["outOfBedSegments"] = [{"startTime": utc(t + 3000), "endTime": utc(t + 4000)}]
        got = [(r.ts - t, r.value) for r in health.sleep_readings(s)]
        self.assertEqual(got, [(0, 3), (3000, 0), (4000, 2), (7200, 0)])

    def test_a_classic_sleep_without_stages_is_asleep(self):
        t = NOW - 3600
        s = sleep(t, [], t + 1800)["sleep"]
        self.assertEqual([r.value for r in health.sleep_readings(s)], [health.SLEEP_CODES["ASLEEP"], 0])


class PollTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)
        self.store = Store(self.dir / "x.sqlite3")
        self.addCleanup(self.store.close)
        patch = mock.patch.object(health, "PAUSE", 0)
        patch.start()
        self.addCleanup(patch.stop)

    def rows(self, quantity):
        return [(ts, v) for ts, _, v in self.store.rows(quantity, 0, NOW + 86400)]

    def test_pages_are_followed_and_the_filter_names_the_type(self):
        points = {"heart-rate": [heart_rate(NOW - i * 5, 60 + i) for i in range(5)]}
        session = FakeSession(points)
        health.poll_type(session, self.store, "heart-rate", NOW)
        self.assertEqual(self.rows("health_heart_rate"), [(NOW - i * 5, 60 + i) for i in reversed(range(5))])
        self.assertEqual(len(session.asked), health.MAX_BACKFILL // health.CHUNK + 2)  # a request a day, three pages the last
        field = "heart_rate.sample_time.physical_time"
        start = NOW - health.MAX_BACKFILL
        self.assertEqual(session.asked[0][1], f'{field} >= "{utc(start)}" AND {field} < "{utc(start + health.CHUNK)}"')
        self.assertEqual(session.asked[-1][1], f'{field} >= "{utc(NOW - health.CHUNK)}"')

    def test_a_catch_up_is_fetched_and_stored_a_day_at_a_time(self):
        newest = NOW - 3.5 * 86400
        self.store.add([health.Reading(newest, "health_heart_rate", 60)])
        points = {"heart-rate": [heart_rate(NOW - i * 3600, i) for i in range(4 * 24) if NOW - i * 3600 >= newest]}
        session = FakeSession(points, page=1000)
        stored = []
        replace = self.store.replace
        with mock.patch.object(self.store, "replace", side_effect=lambda *a: stored.append(len(a[3])) or replace(*a)):
            n = health.poll_type(session, self.store, "heart-rate", NOW)
        self.assertEqual(n, len(points["heart-rate"]))
        self.assertEqual(len(session.asked), 4)  # 3.25 days from the newest less the late window
        self.assertLessEqual(max(stored), 24)
        self.assertEqual(self.rows("health_heart_rate"), sorted((NOW - i * 3600, i) for i in range(85)))  # the newest re-read

    def test_a_window_starting_mid_second_stores_no_reading_twice(self):
        now = NOW + 0.5  # the backfill limit then starts mid-second, and the API's times are whole seconds
        oldest = NOW - health.MAX_BACKFILL
        self.store.add([health.Reading(oldest, "health_heart_rate", 59)])  # stored by the poll before
        health.poll_type(FakeSession({"heart-rate": [heart_rate(oldest, 59)]}), self.store, "heart-rate", now)
        self.assertEqual(self.rows("health_heart_rate"), [(oldest, 59)])

    def test_the_phone_steps_are_dropped(self):
        session = FakeSession({"steps": [steps(NOW - 60, 100), steps(NOW - 60, 98, PHONE), steps(NOW - 120, 7, PHONE)]})
        health.poll_type(session, self.store, "steps", NOW)
        self.assertEqual(self.rows("health_steps"), [(NOW - 60, 100)])

    def test_polling_again_rereads_the_late_window_without_duplicates(self):
        points = {"heart-rate": [heart_rate(NOW - 600, 70)]}
        health.poll_type(FakeSession(points), self.store, "heart-rate", NOW)
        points["heart-rate"].insert(0, heart_rate(NOW - 300, 71))  # synced late
        session = FakeSession(points)
        health.poll_type(session, self.store, "heart-rate", NOW + 900)
        self.assertEqual(self.rows("health_heart_rate"), [(NOW - 600, 70), (NOW - 300, 71)])
        self.assertIn(utc(NOW - 600 - health.LATE), session.asked[0][1])

    def test_a_reprocessed_sleep_replaces_the_old_one(self):
        t = NOW - 8 * 3600
        first = sleep(t, [stage(t, t + 3600, "LIGHT")], t + 3600)
        health.poll_type(FakeSession({"sleep": [first]}), self.store, "sleep", NOW)
        again = sleep(t, [stage(t, t + 1800, "LIGHT"), stage(t + 1800, t + 3600, "DEEP")], t + 3600)
        health.poll_type(FakeSession({"sleep": [again]}), self.store, "sleep", NOW)
        self.assertEqual(self.rows("health_sleep"), [(t, 3), (t + 1800, 4), (t + 3600, 0)])

    def test_daily_types_land_on_local_midnight(self):
        day = {"year": 2026, "month": 10, "day": 18}
        points = {
            "daily-sleep-temperature-derivations": [
                {"dataSource": FITBIT, "dailySleepTemperatureDerivations": {
                    "date": day, "nightlyTemperatureCelsius": 33.5, "baselineTemperatureCelsius": 33.1}}
            ]
        }
        session = FakeSession(points)
        health.poll_type(session, self.store, "daily-sleep-temperature-derivations", NOW)
        midnight = dt.datetime(2026, 10, 18).timestamp()
        self.assertEqual(self.rows("health_skin_temperature"), [(midnight, 33.5)])
        self.assertEqual(self.rows("health_skin_temperature_baseline"), [(midnight, 33.1)])
        self.assertTrue(session.asked[0][1].startswith('daily_sleep_temperature_derivations.date >= "'))

    def test_breathing_rate_takes_the_whole_sleep(self):
        summary = {"sampleTime": {"physicalTime": utc(NOW - 3600)}, "deepSleepStats": {"breathsPerMinute": 15.8},
                   "fullSleepStats": {"breathsPerMinute": 14.9, "standardDeviation": 1, "signalToNoise": 5.9}}
        session = FakeSession({"respiratory-rate-sleep-summary": [{"dataSource": FITBIT, "respiratoryRateSleepSummary": summary}]})
        health.poll_type(session, self.store, "respiratory-rate-sleep-summary", NOW)
        self.assertEqual(self.rows("health_breathing_rate"), [(NOW - 3600, 14.9)])

    def test_one_type_failing_keeps_the_others(self):
        class Flaky(FakeSession):
            def get(self, url):
                if "/steps/" in url:
                    raise RuntimeError("HTTP 500")
                return super().get(url)

        with self.assertRaisesRegex(RuntimeError, "steps: HTTP 500"):
            health.poll_once(Flaky({"heart-rate": [heart_rate(NOW - 5, 61)]}), self.store, NOW, pause=0)
        self.assertEqual(self.rows("health_heart_rate"), [(NOW - 5, 61)])


class LoginTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)

    def test_the_client_must_be_a_desktop_one(self):
        path = self.dir / "client.json"
        self.assertIsNone(health.load_client(path))
        path.write_text(json.dumps({"web": {"client_id": "x", "client_secret": "y"}}))
        with self.assertRaisesRegex(ValueError, "Desktop app"):
            health.load_client(path)
        path.write_text(json.dumps({"installed": {"client_id": "x", "client_secret": "y"}}))
        self.assertEqual(health.load_client(path)["client_id"], "x")

    def test_no_token_means_log_in(self):
        session = health.Session({"client_id": "x", "client_secret": "y"}, self.dir / "token.json")
        with self.assertRaises(health.LoginNeeded):
            session.token()

    def test_the_access_token_is_reused_until_it_expires(self):
        (self.dir / "token.json").write_text(json.dumps({"refresh_token": "r"}))
        session = health.Session({"client_id": "x", "client_secret": "y"}, self.dir / "token.json")
        with mock.patch.object(health, "_post", return_value={"access_token": "a", "expires_in": 3599}) as post:
            self.assertEqual(session.token(), "a")
            self.assertEqual(session.token(), "a")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[1]["refresh_token"], "r")


if __name__ == "__main__":
    unittest.main()
