"""The dashboard: a few JSON endpoints plus static files, on the standard library."""

from __future__ import annotations

import json
import logging
import time
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from . import astro, filter_health, kabbalah, nea, oracle, prophecy, tokens, weather
from .device import Reading
from .recorder import RecorderStatus
from .store import Store, is_meter

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}
CHART_POINTS = 600
# Not blueair_co2: it is recorded, but it is an estimate from the VOC sensor, not CO2 (docs/archive/blueair-eco2.md).
CHART_QUANTITIES = ("co2", "temperature", "humidity") + tuple(
    "blueair_" + q for q in ("pm1", "pm25", "pm10", "voc", "all_pollution", "temperature", "humidity")
)
ORACLE_POINTS = 2000
ORACLE_QUANTITIES = ("humidity",) + tuple("blueair_" + q for q in ("pm25", "voc", "temperature", "humidity", "fan_speed"))
# The first reading of each household member, its birthday.
BIRTHS = {"zytemp": "co2", "blueair": "blueair_*", "island": nea.PREFIX + "*", "weather": weather.PREFIX + "temperature_*"}
OUTDOOR_FRESH = 3 * 3600  # seconds an outdoor PM2.5 reading stays good for advice; NEA's are hourly
COOKIE = "aeromancer"
FOREVER = 10 * 365 * 86400  # a cookie's lifetime for a token that never expires
MAX_BODY = 2 << 20  # bytes of an upload
MAX_READINGS = 5000  # per upload
EXPIRED_PAGE = b"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aeromancer</title><body style="font-family: system-ui, sans-serif; margin: 3rem 1rem; text-align: center">
<h1>Aeromancer</h1><p>This link has expired or is not valid. Ask for a new one.</p></body>"""


def parse_range(text: str) -> float | None:
    """'90m', '6h', '7d' -> seconds; 'all' -> None."""
    if text == "all":
        return None
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if text and text[-1] in units:
        return float(text[:-1]) * units[text[-1]]
    return float(text)


def _window(store: Store, range_text: str) -> tuple[float, float]:
    end = time.time()
    seconds = parse_range(range_text)
    if seconds is None:
        span = store.span()
        return (span[0] if span else end - 3600), end
    return end - seconds, end


def _points(rows) -> list[tuple[float, float]]:
    return [(ts, mean) for ts, mean, _, _ in rows]


def _divination_window(store: Store, range_text: str):
    """The window's start, end and bucket, and a function giving a quantity's points in it at that resolution."""
    start, end = _window(store, range_text)
    bucket = max(1.0, (end - start) / ORACLE_POINTS)

    def points(quantity):
        return _points(store.series(quantity, start, end, bucket))

    return start, end, bucket, points


def outdoor_pm25_now(store: Store, region: str | None) -> float | None:
    """NEA's latest PM2.5 for ``region``, or None when there is none fresh enough to go by."""
    row = store.latest_of(nea.PREFIX + region) if region else None
    return row[1] if row and time.time() - row[0] < OUTDOOR_FRESH else None


def _household(store: Store, range_text: str, outdoor_region: str | None, home) -> dict:
    """What the Oracle and the council of seers read: the window's series, under the Oracle's names."""
    start, end, bucket, points = _divination_window(store, range_text)
    others = {q: points(q) for q in ORACLE_QUANTITIES}
    regions = {r: points(nea.PREFIX + r) for r in nea.REGIONS}
    if outdoor_region:
        others["outdoor_pm25"] = regions[outdoor_region]
    others["outdoor_temperature"] = _points(weather.home_series(store, home, "temperature", start, end, bucket))
    others["outdoor_humidity"] = _points(weather.home_series(store, home, "humidity", start, end, bucket))
    # One reading each, unaveraged: wind is paired by time and rain is summed, and degrees do not average.
    for kind in ("wind_speed", "wind_direction", "rain"):
        others["outdoor_" + kind] = _points(weather.home_series(store, home, kind, start, end, 1))
    return {
        "co2": points("co2"),
        "start": start,
        "end": end,
        "others": {q: p for q, p in others.items() if p},
        "regions": {r: p for r, p in regions.items() if p},
        "placements": store.placements(),
        "home": home,
        "outdoor_pm25": outdoor_pm25_now(store, outdoor_region),
        "points": points,
    }


def run_oracle(store: Store, range_text: str, outdoor_region: str | None = None, home=None) -> dict:
    household = _household(store, range_text, outdoor_region, home)
    points, end = household.pop("points"), household["end"]
    signals = {name: p for name in store.signal_names() if (p := points(name))}
    born = {member: ts for member, pattern in BIRTHS.items() if (ts := store.first_ts(pattern)) is not None}
    # The I Ching's casters over the day before the hour, whatever the window.
    day = end - astro.DAY
    recent = {q: _points(store.series(q, day, end, 300)) for q in ("co2", "temperature", "blueair_pm25", "blueair_temperature")}
    recent["outdoor_pm25"] = _points(store.series(nea.PREFIX + outdoor_region, day, end, 300)) if outdoor_region else []
    recent["outdoor_wind_speed"] = _points(weather.home_series(store, home, "wind_speed", day, end, 300))
    return oracle.analyze(temperature=points("temperature"), signals=signals, born=born, recent=recent, **household)


def run_prophecy(store: Store, range_text: str, outdoor_region: str | None = None, home=None) -> dict:
    household = _household(store, range_text, outdoor_region, home)
    del household["points"]
    return prophecy.analyze(**household)


def run_kabbalah(store: Store, range_text: str, outdoor_region: str | None = None, home=None) -> dict:
    start, end, bucket, points = _divination_window(store, range_text)
    series = {key: points(key) for key in kabbalah.INSTRUMENTS if not key.startswith("outdoor_")}
    # Under generic names, as on the charts, so the dashboard does not say where home is.
    series["outdoor_pm25"] = points(nea.PREFIX + outdoor_region) if outdoor_region else []
    for kind in ("temperature", "humidity", "rain", "wind_speed"):
        series["outdoor_" + kind] = _points(weather.home_series(store, home, kind, start, end, bucket))
    return kabbalah.analyze(series, end, outdoor_pm25_now(store, outdoor_region))


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address,
        db_path,
        recorder: RecorderStatus | None,
        outdoor_region: str | None = None,
        home=None,
        filter_settings: filter_health.Settings | None = None,
        auth: bool = False,
    ):
        super().__init__(address, Handler)
        self.db_path = db_path
        self.recorder = recorder
        self.outdoor_region = outdoor_region
        self.home = home
        self.filter_settings = filter_settings
        self.auth = auth  # when hosted: every request needs a token (tokens.py), and machines may upload


class Handler(BaseHTTPRequestHandler):
    server: DashboardServer

    def log_message(self, fmt, *args):
        log.debug("%s " + fmt, self.address_string(), *args)

    def do_GET(self):
        url = urlsplit(self.path)
        query = {k: v[-1] for k, v in parse_qs(url.query).items()}
        if self.server.auth and not self._admit(url, query):
            return
        if url.path in STATIC_FILES:
            name, content_type = STATIC_FILES[url.path]
            return self._send(HTTPStatus.OK, (STATIC_DIR / name).read_bytes(), content_type)
        api = {
            "/api/latest": self.latest,
            "/api/series": self.series,
            "/api/oracle": self.oracle,
            "/api/kabbalah": self.kabbalah,
            "/api/prophecy": self.prophecy,
            "/api/filter": self.filter,
            "/api/placements": self.placements,
        }.get(url.path)
        if api is None:
            return self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
        self._answer(lambda: self._with_store(True, lambda store: api(store, query)))

    def do_POST(self):
        path = urlsplit(self.path).path
        api = {"/api/readings": self.upload, "/api/placements": self.place}.get(path)
        if not self.server.auth or api is None:
            return self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
        if not self._writer():
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"at most {MAX_BODY} bytes".encode(), "text/plain")
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError:
            return self._send(HTTPStatus.BAD_REQUEST, b"not JSON", "text/plain")
        self._answer(lambda: self._with_store(False, lambda store: api(store, body)))

    def do_DELETE(self):
        path = urlsplit(self.path).path
        prefix = "/api/placements/"
        if not self.server.auth or not path.startswith(prefix) or not path[len(prefix) :].isdigit():
            return self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
        if not self._writer():
            return
        id = int(path[len(prefix) :])
        if not self._with_store(False, lambda store: store.unplace(id)):
            return self._send(HTTPStatus.NOT_FOUND, f"no placement {id}".encode(), "text/plain")
        self._send(HTTPStatus.OK, b"{}", "application/json")

    def _with_store(self, readonly: bool, use):
        """``use(store)``; the dashboard never writes, only uploads do."""
        store = Store(self.server.db_path, readonly=readonly)
        try:
            return use(store)
        finally:
            store.close()

    def _answer(self, compute):
        try:
            body = compute()
        except FileNotFoundError as e:
            return self._send(HTTPStatus.SERVICE_UNAVAILABLE, str(e).encode(), "text/plain")
        except (ValueError, TypeError) as e:  # bad input
            return self._send(HTTPStatus.BAD_REQUEST, str(e).encode(), "text/plain")
        self._send(HTTPStatus.OK, json.dumps(body).encode(), "application/json")

    def _secret(self) -> str | None:
        """The token the request carries: a bearer token (machines) or the cookie a share link set (people)."""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[len("Bearer ") :].strip()
        try:
            morsel = SimpleCookie(self.headers.get("Cookie", "")).get(COOKIE)
        except CookieError:
            return None
        return morsel.value if morsel else None

    def _token(self, secret: str | None, scope: str) -> tokens.Token | None:
        try:
            return self._with_store(True, lambda store: tokens.check(store, secret, scope))
        except FileNotFoundError:
            return None

    def _admit(self, url, query) -> bool:
        """Let a viewer in, or answer for them: a share link's ``?t=`` becomes a cookie, then the address without it."""
        if "t" in query:
            token = self._token(query["t"], "view")
            if token is None:
                self._refuse()
                return False
            rest = urlencode({k: v for k, v in query.items() if k != "t"})
            age = FOREVER if token.expires is None else max(0, int(token.expires - time.time()))
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", url.path + ("?" + rest if rest else ""))
            self.send_header("Set-Cookie", f"{COOKIE}={query['t']}; Max-Age={age}; Path=/; HttpOnly; Secure; SameSite=Lax")
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return False
        secret = self._secret()
        scopes = ("view", "write") if url.path == "/api/placements" else ("view",)  # the place command lists them
        if any(self._token(secret, scope) for scope in scopes):
            return True
        self._refuse(api=url.path.startswith("/api/"))
        return False

    def _writer(self) -> bool:
        if self._token(self._secret(), "write"):
            return True
        self._refuse(api=True)
        return False

    def _refuse(self, api: bool = False):
        if api:
            return self._send(HTTPStatus.UNAUTHORIZED, b"no valid token", "text/plain")
        self._send(HTTPStatus.UNAUTHORIZED, EXPIRED_PAGE, "text/html; charset=utf-8")

    def _send(self, status, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def latest(self, store: Store, query):
        latest = store.latest()
        span = store.span()
        co2 = latest.get("co2")
        return {
            "now": time.time(),
            "latest": {q: {"ts": ts, "value": v} for q, (ts, v) in latest.items()},
            "chakra": oracle.chakra_of(co2[1]) if co2 else None,
            "hazy": oracle.hazy(outdoor_pm25_now(store, self.server.outdoor_region)),
            "first_ts": span[0] if span else None,
            "count": store.count(),
            "recorder": self.server.recorder.snapshot() if self.server.recorder else None,
        }

    def series(self, store: Store, query):
        start, end = _window(store, query.get("range", "24h"))
        bucket = max(1.0, (end - start) / int(query.get("points", CHART_POINTS)))
        series = {q: store.series(q, start, end, bucket) for q in CHART_QUANTITIES}
        # Under a generic name, so the public dashboard does not say where home is.
        region = self.server.outdoor_region
        series["outdoor_pm25"] = []
        if region:
            # Hourly, so the reading before the window too: the chart starts its shading at the window's edge.
            lead = store.latest_of(nea.PREFIX + region, before=start)
            series["outdoor_pm25"] = [(lead[0], lead[1], lead[1], lead[1])] if lead else []
            series["outdoor_pm25"] += store.series(nea.PREFIX + region, start, end, bucket)
        for kind in ("temperature", "humidity"):
            series["outdoor_" + kind] = weather.home_series(store, self.server.home, kind, start, end, bucket)
        return {
            "start": start,
            "end": end,
            "bucket": bucket,
            "series": series,
            "retrograde": astro.mercury_retrograde_intervals(start, end),
            "lunations": astro.lunations(start, end),
            "moves": [
                {"ts": m.ts, "device": m.device, "room": m.room, "spot": m.spot}
                for m in store.placements()
                if start < m.ts <= end
            ],
        }

    def oracle(self, store: Store, query):
        return run_oracle(store, query.get("range", "24h"), self.server.outdoor_region, self.server.home)

    def kabbalah(self, store: Store, query):
        return run_kabbalah(store, query.get("range", "24h"), self.server.outdoor_region, self.server.home)

    def prophecy(self, store: Store, query):
        return run_prophecy(store, query.get("range", "24h"), self.server.outdoor_region, self.server.home)

    def filter(self, store: Store, query):
        return filter_health.status(store, self.server.filter_settings)

    def placements(self, store: Store, query):
        return [
            {"id": p.id, "ts": p.ts, "device": p.device, "room": p.room, "spot": p.spot}
            for p in store.placements(query.get("device"))
        ]

    def upload(self, store: Store, body):
        """A recording machine's meter readings, ``{"readings": [[ts, quantity, value], ...]}``; repeats are skipped."""
        rows = body.get("readings") if isinstance(body, dict) else None
        if not isinstance(rows, list) or len(rows) > MAX_READINGS:
            raise ValueError(f"expected {{'readings': [[ts, quantity, value], ...]}}, at most {MAX_READINGS}")
        readings = []
        for row in rows:
            if not (isinstance(row, list) and len(row) == 3 and isinstance(row[1], str)):
                raise ValueError(f"not [ts, quantity, value]: {row!r}")
            if not is_meter(row[1]):
                raise ValueError(f"{row[1]!r} is not the meter's; the server polls the rest itself")
            readings.append(Reading(float(row[0]), row[1], float(row[2])))
        return {"added": store.add_new(readings)}

    def place(self, store: Store, body):
        """``{"ts", "device", "room", "spot"}``, as the place command records it."""
        if not isinstance(body, dict) or not {"ts", "device", "room"} <= body.keys():
            raise ValueError("expected {'ts', 'device', 'room', 'spot'}")
        return {"id": store.place(float(body["ts"]), str(body["device"]), str(body["room"]), str(body.get("spot", "")))}


def serve(
    db_path,
    host: str,
    port: int,
    recorder: RecorderStatus | None = None,
    outdoor_region: str | None = None,
    home=None,
    filter_settings: filter_health.Settings | None = None,
    auth: bool = False,
) -> None:
    server = DashboardServer((host, port), db_path, recorder, outdoor_region, home, filter_settings, auth)
    log.info("dashboard at http://%s:%d/", host, port)
    server.serve_forever()
