import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from aeromancer import push, server, tokens
from aeromancer.device import Reading
from aeromancer.store import Store

START = 1_790_000_000.0


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch(url, method="GET", body=None, headers=None):
    """``(status, headers, body)``, without following redirects."""
    request = urllib.request.Request(url, None if body is None else json.dumps(body).encode(), headers or {}, method=method)
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


class HostedTest(unittest.TestCase):
    """The dashboard as ``host`` serves it: only to token holders, and taking the meter's uploads."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.db = Path(self.dir.name) / "server.sqlite3"
        store = Store(self.db)
        store.add([Reading(START, "co2", 600)])
        self.view = tokens.issue(store, "alice", "view", 3600)
        self.write = tokens.issue(store, "laptop", "write", None)
        self.expired = tokens.issue(store, "bob", "view", 1, now=time.time() - 10)
        store.close()
        self.server = server.DashboardServer(("127.0.0.1", 0), self.db, None, auth=True)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.dir.cleanup()

    def readings(self):
        store = Store(self.db, readonly=True)
        try:
            return store.db.execute("SELECT ts, quantity, value FROM readings ORDER BY ts, quantity").fetchall()
        finally:
            store.close()

    def test_nothing_without_a_token(self):
        for path in ("/", "/app.js", "/api/latest"):
            self.assertEqual(fetch(self.url + path)[0], 401, path)

    def test_share_link_sets_a_cookie_and_drops_the_token(self):
        status, headers, _ = fetch(f"{self.url}/?t={self.view}")
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/")
        cookie = headers["Set-Cookie"]
        self.assertIn(f"{server.COOKIE}={self.view}", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertLessEqual(int(cookie.split("Max-Age=")[1].split(";")[0]), 3600)
        status, _, body = fetch(self.url + "/api/latest", headers={"Cookie": cookie.split(";")[0]})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["latest"]["co2"]["value"], 600)

    def test_expired_link_is_refused(self):
        status, _, body = fetch(f"{self.url}/?t={self.expired}")
        self.assertEqual(status, 401)
        self.assertIn(b"expired", body)

    def test_write_token_uploads_but_cannot_view(self):
        bearer = {"Authorization": f"Bearer {self.write}"}
        self.assertEqual(fetch(self.url + "/api/latest", headers=bearer)[0], 401)
        rows = {"readings": [[START, "co2", 600], [START + 5, "co2", 610], [START + 5, "op_6e", 27160]]}
        status, _, body = fetch(self.url + "/api/readings", "POST", rows, bearer)
        self.assertEqual((status, json.loads(body)), (200, {"added": 2}))  # the first was there already
        status, _, body = fetch(self.url + "/api/readings", "POST", rows, bearer)
        self.assertEqual(json.loads(body), {"added": 0})
        self.assertEqual(len(self.readings()), 3)

    def test_uploads_only_the_meter_and_only_with_a_write_token(self):
        rows = {"readings": [[START + 5, "co2", 610]]}
        self.assertEqual(fetch(self.url + "/api/readings", "POST", rows, {"Authorization": f"Bearer {self.view}"})[0], 401)
        bearer = {"Authorization": f"Bearer {self.write}"}
        self.assertEqual(fetch(self.url + "/api/readings", "POST", {"readings": [[START, "blueair_pm25", 3]]}, bearer)[0], 400)
        self.assertEqual(fetch(self.url + "/api/readings", "POST", {"readings": [[None, "co2", 3]]}, bearer)[0], 400)
        self.assertEqual(len(self.readings()), 1)

    def test_placements_through_the_api(self):
        remote = push.Remote(self.url, self.write)
        added = push.call(remote, "POST", "/api/placements", {"ts": START, "device": "zytemp", "room": "office", "spot": ""})
        (placement,) = push.call(remote, "GET", "/api/placements")
        self.assertEqual((placement["id"], placement["room"]), (added["id"], "office"))
        push.call(remote, "DELETE", f"/api/placements/{added['id']}")
        self.assertEqual(push.call(remote, "GET", "/api/placements"), [])
        with self.assertRaises(RuntimeError):
            push.call(remote, "DELETE", f"/api/placements/{added['id']}")

    def test_pusher_uploads_the_meter_and_resumes(self):
        local = Store(Path(self.dir.name) / "laptop.sqlite3")
        local.add([Reading(START + i, "co2", 500 + i) for i in range(7)] + [Reading(START, "blueair_pm25", 3)])
        remote = push.Remote(self.url, self.write)
        self.assertEqual(push.push_once(local, remote, batch=3), 7)
        self.assertEqual(push.push_once(local, remote), 0)
        local.add([Reading(START + 100, "temperature", 21.5)])
        with mock.patch.object(push, "call", side_effect=urllib.error.URLError("offline")):
            with self.assertRaises(OSError):
                push.push_once(local, remote)
        self.assertEqual(push.push_once(local, remote), 1)  # what failed goes up next time
        local.close()
        quantities = [q for _, q, _ in self.readings()]
        self.assertEqual(quantities.count("co2"), 7)  # START's was there already
        self.assertNotIn("blueair_pm25", quantities)

    def test_unhosted_dashboard_takes_no_uploads(self):
        plain = server.DashboardServer(("127.0.0.1", 0), self.db, None)
        threading.Thread(target=plain.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{plain.server_port}"
            self.assertEqual(fetch(url + "/api/readings", "POST", {"readings": []})[0], 404)
            self.assertEqual(fetch(url + "/api/latest")[0], 200)
        finally:
            plain.shutdown()
            plain.server_close()


if __name__ == "__main__":
    unittest.main()
