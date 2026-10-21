"""Polls what a Fitbit or Pixel Watch recorded, through the Google Health API.

The bracelet syncs to the Google Health app on the phone, and the app to
Google's cloud, every 15 minutes or so, or hours late when the phone is
away. Every ``POLL_SECONDS`` this reads each data type from a little before
its newest stored reading up to now, and replaces what was stored in that
window, so that late syncs and reprocessed sleep land too.

Stored as ``health_<field>``:

- ``heart_rate`` (bpm, every 2-5 s), ``hrv`` (RMSSD in ms, every 5 minutes
  of sleep), ``spo2`` (%, about each minute of sleep the device trusts),
  ``steps`` (per minute, at the minute's start; the phone's own count is dropped)
- ``breathing_rate`` (breaths/min, one per sleep, at its end)
- ``resting_heart_rate``, ``skin_temperature`` and ``skin_temperature_baseline``
  (°C), one per day, at the day's local midnight
- ``sleep``: the sleep stage from each stage's start on, as ``SLEEP_CODES``;
  0 when a sleep ends or the sleeper gets out of bed. The short awakenings,
  which overlap the stages, are not stored.

Needs an OAuth client of the Google Cloud project that has the Google Health
API (docs/health.md), downloaded as ``~/.config/aeromancer/google-health-client.json``.
``aeromancer health-login`` asks for consent and keeps the refresh
token in ``~/.config/aeromancer/google-health-token.json``.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import logging
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .device import Reading
from .store import Store

log = logging.getLogger(__name__)

PREFIX = "health_"
API = "https://health.googleapis.com/v4/users/me/dataTypes"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = tuple(
    "https://www.googleapis.com/auth/googlehealth." + s
    for s in ("activity_and_fitness.readonly", "health_metrics_and_measurements.readonly", "sleep.readonly")
)
POLL_SECONDS = 900.0
LATE = 6 * 3600  # re-read this far before the newest stored reading: the phone syncs in batches, and sleep is reprocessed
MAX_BACKFILL = 30 * 86400  # seconds
PAGE_SIZE = 10000  # the API's maximum; 25 for sleep
PAUSE = 1.0  # seconds between requests
PHONE = "MobileTrack"  # the device name of the phone's own step count, which counts the same walks as the wearable

# Sleep stage -> the code stored in health_sleep, deeper higher, as a hypnogram draws them. A "classic" sleep, which
# the device records when it cannot tell the stages apart (a short nap, a loose band), has asleep, restless and awake.
SLEEP_CODES = {"AWAKE": 1, "RESTLESS": 1.5, "REM": 2, "ASLEEP": 2.5, "LIGHT": 3, "DEEP": 4}
OUT_OF_SLEEP = 0


class LoginNeeded(Exception):
    """No refresh token, or Google no longer takes it: run ``health-login``."""


def _config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")) / "aeromancer"


def default_client_path() -> Path:
    return _config_dir() / "google-health-client.json"


def default_token_path() -> Path:
    return _config_dir() / "google-health-token.json"


def load_client(path: str | os.PathLike) -> dict | None:
    """The OAuth client as the Cloud console downloads it (``{"installed": {...}}``), or None when there is no file."""
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return None
    client = data.get("installed") if isinstance(data, dict) else None
    if not isinstance(client, dict) or not {"client_id", "client_secret"} <= client.keys():
        raise ValueError(f"{path} is not a desktop OAuth client: create one of type 'Desktop app' (docs/health.md)")
    return client


def _post(url: str, form: dict) -> dict:
    request = urllib.request.Request(url, urllib.parse.urlencode(form).encode(), headers={"User-Agent": "aeromancer"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        if e.code == 400 and "invalid_grant" in body:
            raise LoginNeeded("Google refused the refresh token (expired or revoked); run health-login again") from None
        raise RuntimeError(f"{url}: HTTP {e.code}: {body[:300]}") from None


def login(client: dict, token_path: str | os.PathLike, open_browser: bool = True) -> None:
    """Ask for consent in the browser, catch the redirect on localhost, and save the refresh token."""
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(16)
    got: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
            if "code" not in query and "error" not in query:
                self.send_error(404)
                return
            got.update(query)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Aeromancer: done, you can close this tab.\n".encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    redirect = f"http://127.0.0.1:{server.server_port}"
    url = AUTH_URL + "?" + urllib.parse.urlencode(
        {
            "client_id": client["client_id"],
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",  # else Google sends a refresh token only the first time
            "state": state,
            "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode(),
            "code_challenge_method": "S256",
        }
    )
    print(f"Open this in a browser and allow access:\n\n{url}\n")
    if open_browser:
        webbrowser.open(url)
    with server:
        while not got:
            server.handle_request()
    if got.get("state") != state:
        raise RuntimeError("the redirect's state does not match; try again")
    if "error" in got:
        raise RuntimeError(f"Google said: {got['error']}")
    granted = set(got.get("scope", "").split())
    if missing := [s for s in SCOPES if s not in granted]:
        log.warning("not granted, so not polled: %s", ", ".join(s.rsplit(".", 2)[-2] for s in missing))
    token = _post(
        client.get("token_uri", TOKEN_URL),
        {
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "code": got["code"],
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect,
        },
    )
    if "refresh_token" not in token:
        raise RuntimeError("Google sent no refresh token; remove aeromancer's access in your Google account and try again")
    path = Path(token_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"refresh_token": token["refresh_token"], "scope": token.get("scope", ""), "saved": time.time()}, f)
    print(f"Saved the refresh token to {path}")


class Session:
    """Access tokens from the saved refresh token, re-read each time one is needed, so a new login is picked up."""

    def __init__(self, client: dict, token_path: str | os.PathLike):
        self.client, self.token_path = client, Path(token_path)
        self.access, self.expires = None, 0.0

    def token(self) -> str:
        if self.access is None or time.time() > self.expires - 60:
            try:
                refresh = json.loads(self.token_path.read_text())["refresh_token"]
            except FileNotFoundError:
                raise LoginNeeded(f"no {self.token_path}; run health-login") from None
            got = _post(
                self.client.get("token_uri", TOKEN_URL),
                {
                    "client_id": self.client["client_id"],
                    "client_secret": self.client["client_secret"],
                    "refresh_token": refresh,
                    "grant_type": "refresh_token",
                },
            )
            self.access, self.expires = got["access_token"], time.time() + float(got.get("expires_in", 3600))
        return self.access

    def get(self, url: str) -> dict:
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token()}", "User-Agent": "aeromancer"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self.access = None
            raise RuntimeError(f"{url}: HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from None


def _rfc3339(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts(text: str) -> float:
    return dt.datetime.fromisoformat(text).timestamp()


def _midnight(date: dict) -> float:
    """``{"year": 2026, "month": 10, "day": 18}`` -> unix time of that local midnight."""
    return dt.datetime(date["year"], date["month"], date["day"]).timestamp()


# Each data type's points -> readings.
def _heart_rate(p):
    return [Reading(_ts(p["sampleTime"]["physicalTime"]), PREFIX + "heart_rate", float(p["beatsPerMinute"]))]


def _hrv(p):
    if "rootMeanSquareOfSuccessiveDifferencesMilliseconds" not in p:
        return []
    return [Reading(_ts(p["sampleTime"]["physicalTime"]), PREFIX + "hrv", float(p["rootMeanSquareOfSuccessiveDifferencesMilliseconds"]))]


def _spo2(p):
    return [Reading(_ts(p["sampleTime"]["physicalTime"]), PREFIX + "spo2", float(p["percentage"]))]


def _steps(p):
    return [Reading(_ts(p["interval"]["startTime"]), PREFIX + "steps", float(p["count"]))]


def _breathing_rate(p):
    stats = p.get("fullSleepStats") or {}
    rate = stats.get("breathsPerMinute")
    return [] if rate is None else [Reading(_ts(p["sampleTime"]["physicalTime"]), PREFIX + "breathing_rate", float(rate))]


def _resting_heart_rate(p):
    return [Reading(_midnight(p["date"]), PREFIX + "resting_heart_rate", float(p["beatsPerMinute"]))]


def _skin_temperature(p):
    out = []
    for field, quantity in (("nightlyTemperatureCelsius", "skin_temperature"), ("baselineTemperatureCelsius", "skin_temperature_baseline")):
        if field in p:
            out.append(Reading(_midnight(p["date"]), PREFIX + quantity, float(p[field])))
    return out


FILTERS = {"sample": "sample_time.physical_time", "interval": "interval.start_time"}
# data type -> (JSON field of its points, how it is timed, parser, the quantities it fills)
TYPES = {
    "heart-rate": ("heartRate", "sample", _heart_rate, ("heart_rate",)),
    "heart-rate-variability": ("heartRateVariability", "sample", _hrv, ("hrv",)),
    "oxygen-saturation": ("oxygenSaturation", "sample", _spo2, ("spo2",)),
    "steps": ("steps", "interval", _steps, ("steps",)),
    "respiratory-rate-sleep-summary": ("respiratoryRateSleepSummary", "sample", _breathing_rate, ("breathing_rate",)),
    "daily-resting-heart-rate": ("dailyRestingHeartRate", "date", _resting_heart_rate, ("resting_heart_rate",)),
    "daily-sleep-temperature-derivations": (
        "dailySleepTemperatureDerivations", "date", _skin_temperature, ("skin_temperature", "skin_temperature_baseline"),
    ),
}


def sleep_readings(sleep: dict) -> list[Reading]:
    """One sleep -> ``health_sleep``: each stage's code from its start, 0 out of bed and from the sleep's end on."""
    end = _ts(sleep["interval"]["endTime"])
    stages = sorted((_ts(s["startTime"]), SLEEP_CODES.get(s["type"], SLEEP_CODES["ASLEEP"])) for s in sleep.get("stages", []))
    if not stages:
        stages = [(_ts(sleep["interval"]["startTime"]), SLEEP_CODES["ASLEEP"])]
    out = [(_ts(s["startTime"]), _ts(s["endTime"])) for s in sleep.get("outOfBedSegments", [])]

    def stage_at(t):
        return next((code for ts, code in reversed(stages) if ts <= t), SLEEP_CODES["ASLEEP"])

    events = [(t, code) for t, code in stages if not any(a <= t < b for a, b in out)]
    events += [(a, OUT_OF_SLEEP) for a, _ in out] + [(b, stage_at(b)) for _, b in out]
    events = sorted(e for e in events if e[0] < end) + [(end, OUT_OF_SLEEP)]
    return [Reading(ts, PREFIX + "sleep", float(code)) for ts, code in events]


def fetch(session: Session, data_type: str, filter_: str) -> list[dict]:
    """Every data point of ``data_type`` matching ``filter_``, over all the pages."""
    points, token = [], None
    while True:
        query = {"filter": filter_, "pageSize": 25 if data_type == "sleep" else PAGE_SIZE}
        if token:
            query["pageToken"] = token
        page = session.get(f"{API}/{data_type}/dataPoints?{urllib.parse.urlencode(query)}")
        points += page.get("dataPoints", [])
        token = page.get("nextPageToken")
        if not token:
            return points
        time.sleep(PAUSE)


def _device(point: dict) -> str | None:
    return ((point.get("dataSource") or {}).get("device") or {}).get("displayName")


def _window(store: Store, quantities, now: float) -> float:
    newest = max((store.last_ts(PREFIX + q) or 0.0 for q in quantities), default=0.0)
    return max(newest - LATE, now - MAX_BACKFILL)


def poll_type(session: Session, store: Store, data_type: str, now: float) -> int:
    """Re-read ``data_type`` from a little before its newest stored reading; return how many readings it has there."""
    if data_type == "sleep":
        # A sleep is found by its end; one still being stored can end after now, so look a sleep's length ahead too.
        since = _window(store, ("sleep",), now) - 86400
        sleeps = [p["sleep"] for p in fetch(session, "sleep", f'sleep.interval.end_time >= "{_rfc3339(since)}"')]
        readings = []
        for sleep in sleeps:
            new = sleep_readings(sleep)
            store.replace(PREFIX + "sleep", new[0].ts, new[-1].ts, new)  # it may have been reprocessed since
            readings += new
        return len(readings)
    field, kind, parse, quantities = TYPES[data_type]
    since = _window(store, quantities, now)
    name = data_type.replace("-", "_")  # as filters name it
    if kind == "date":
        since = dt.datetime.fromtimestamp(since).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        filter_ = f'{name}.date >= "{dt.date.fromtimestamp(since).isoformat()}"'
    else:
        filter_ = f'{name}.{FILTERS[kind]} >= "{_rfc3339(since)}"'
    points = [p for p in fetch(session, data_type, filter_) if field in p and _device(p) != PHONE]
    readings = [r for p in points for r in parse(p[field])]
    for q in quantities:
        mine = [r for r in readings if r.quantity == PREFIX + q]
        store.replace(PREFIX + q, since, max(now, *(r.ts for r in mine)) if mine else now, mine)
    return len(readings)


def poll_once(session: Session, store: Store, now: float | None = None, pause: float = PAUSE) -> int:
    """Re-read every data type; return how many readings. One failing does not stop the others."""
    now = time.time() if now is None else now
    total, failed = 0, []
    for i, data_type in enumerate(("sleep", *TYPES)):
        if i:
            time.sleep(pause)
        try:
            total += poll_type(session, store, data_type, now)
        except LoginNeeded:
            raise
        except Exception as e:
            failed.append(f"{data_type}: {e or type(e).__name__}")
    if failed:
        raise RuntimeError("; ".join(failed))
    return total


def poll(db_path, client: dict, token_path, stop: threading.Event | None = None) -> None:
    """Poll until ``stop`` is set, retrying after any failure."""
    stop = stop or threading.Event()
    store, session = Store(db_path), Session(client, token_path)
    log.info("polling Google Health into %s", db_path)
    try:
        while not stop.is_set():
            try:
                n = poll_once(session, store)
                log.debug("stored %d Google Health readings", n)
            except Exception as e:  # network, expired login, odd response: try again next time
                log.warning("Google Health: %s; retrying in %.0f s", e or type(e).__name__, POLL_SECONDS)
            stop.wait(POLL_SECONDS)
    finally:
        store.close()


def start_in_background(db_path, client: dict, token_path) -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=poll, args=(db_path, client, token_path, stop), name="health", daemon=True).start()
    return stop
