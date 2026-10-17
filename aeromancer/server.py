"""The dashboard: a few JSON endpoints plus static files, on the standard library."""

from __future__ import annotations

import json
import logging
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import astro, oracle
from .recorder import RecorderStatus
from .store import Store

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}
CHART_POINTS = 600
CHART_QUANTITIES = ("co2", "temperature", "humidity") + tuple(
    "blueair_" + q for q in ("co2", "pm1", "pm25", "pm10", "voc", "all_pollution", "temperature", "humidity")
)
ORACLE_POINTS = 2000


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


def run_oracle(store: Store, range_text: str) -> dict:
    start, end = _window(store, range_text)
    bucket = max(1.0, (end - start) / ORACLE_POINTS)

    def points(quantity):
        return _points(store.series(quantity, start, end, bucket))

    signals = {name: p for name in store.signal_names() if (p := points(name))}
    return oracle.analyze(points("co2"), points("temperature"), start, end, signals)


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, db_path, recorder: RecorderStatus | None):
        super().__init__(address, Handler)
        self.db_path = db_path
        self.recorder = recorder


class Handler(BaseHTTPRequestHandler):
    server: DashboardServer

    def log_message(self, fmt, *args):
        log.debug("%s " + fmt, self.address_string(), *args)

    def do_GET(self):
        url = urlsplit(self.path)
        query = {k: v[-1] for k, v in parse_qs(url.query).items()}
        if url.path in STATIC_FILES:
            name, content_type = STATIC_FILES[url.path]
            return self._send(HTTPStatus.OK, (STATIC_DIR / name).read_bytes(), content_type)
        api = {"/api/latest": self.latest, "/api/series": self.series, "/api/oracle": self.oracle}.get(url.path)
        if api is None:
            return self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
        store = Store(self.server.db_path)
        try:
            body = api(store, query)
        except ValueError as e:
            return self._send(HTTPStatus.BAD_REQUEST, str(e).encode(), "text/plain")
        finally:
            store.close()
        self._send(HTTPStatus.OK, json.dumps(body).encode(), "application/json")

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
            "first_ts": span[0] if span else None,
            "count": store.count(),
            "recorder": self.server.recorder.snapshot() if self.server.recorder else None,
        }

    def series(self, store: Store, query):
        start, end = _window(store, query.get("range", "24h"))
        bucket = max(1.0, (end - start) / int(query.get("points", CHART_POINTS)))
        return {
            "start": start,
            "end": end,
            "bucket": bucket,
            "series": {q: store.series(q, start, end, bucket) for q in CHART_QUANTITIES},
            "retrograde": astro.mercury_retrograde_intervals(start, end),
            "lunations": astro.lunations(start, end),
        }

    def oracle(self, store: Store, query):
        return run_oracle(store, query.get("range", "24h"))


def serve(db_path, host: str, port: int, recorder: RecorderStatus | None = None) -> None:
    server = DashboardServer((host, port), db_path, recorder)
    log.info("dashboard at http://%s:%d/", host, port)
    server.serve_forever()
