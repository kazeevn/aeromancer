"""Uploads the meter's readings to the hosted dashboard (docs/cloud.md).

A recording machine keeps its own database, so it records on while offline,
and uploads what the meter said since the last upload every half a minute.
Only the meter's quantities go up: the server polls the outdoor data, the
purifier and the wearable itself. The server skips readings it already has,
so an upload whose answer got lost is simply sent again.

Pushes when ``~/.config/aeromancer/remote.toml`` names the server and a write
token for this machine::

    url = "https://1-2-3-4.sslip.io"
    token = "aer_..."
"""

from __future__ import annotations

import json
import logging
import os
import threading
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .store import Store

log = logging.getLogger(__name__)

POLL_SECONDS = 30.0
BATCH = 5000  # readings per upload, the server's maximum
TIMEOUT = 60.0


@dataclass(frozen=True)
class Remote:
    url: str  # without a trailing slash
    token: str


def default_config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"))
    return base / "aeromancer" / "remote.toml"


def load_remote(path: str | os.PathLike) -> Remote | None:
    """The server to upload to, or None when there is no config file."""
    try:
        with Path(path).open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return None
    url, token = data.get("url"), data.get("token")
    if not isinstance(url, str) or not url.startswith(("https://", "http://")) or not isinstance(token, str):
        raise ValueError(f"{path}: expected url = \"https://...\" and token = \"aer_...\"")
    return Remote(url.rstrip("/"), token)


def call(remote: Remote, method: str, path: str, body=None):
    """The server's JSON answer to ``method path`` with ``body``; RuntimeError on any HTTP error."""
    request = urllib.request.Request(
        remote.url + path,
        None if body is None else json.dumps(body).encode(),
        method=method,
        headers={"Authorization": f"Bearer {remote.token}", "Content-Type": "application/json", "User-Agent": "aeromancer"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{remote.url}{path}: HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from None


def push_once(store: Store, remote: Remote, batch: int = BATCH) -> int:
    """Upload every meter reading not uploaded yet; returns how many were sent."""
    sent = 0
    while rows := store.unpushed(store.push_cursor(remote.url), batch):
        call(remote, "POST", "/api/readings", {"readings": [[ts, q, v] for _, ts, q, v in rows]})
        store.set_push_cursor(remote.url, rows[-1][0])
        sent += len(rows)
    return sent


def push(db_path, remote: Remote, stop: threading.Event | None = None) -> None:
    """Upload until ``stop`` is set, retrying after any failure."""
    stop = stop or threading.Event()
    store = Store(db_path)
    log.info("uploading the meter's readings from %s to %s", db_path, remote.url)
    error = None
    try:
        while not stop.is_set():
            try:
                n = push_once(store, remote)
                log.debug("uploaded %d readings", n)
                if error is not None:
                    log.info("uploading to %s again", remote.url)
                error = None
            except (OSError, RuntimeError, ValueError) as e:  # offline, server down, token revoked
                if str(e) != error:
                    log.warning("upload: %s; retrying every %.0f s", e, POLL_SECONDS)
                error = str(e)
            stop.wait(POLL_SECONDS)
    finally:
        store.close()


def start_in_background(db_path, remote: Remote) -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=push, args=(db_path, remote, stop), name="push", daemon=True).start()
    return stop
