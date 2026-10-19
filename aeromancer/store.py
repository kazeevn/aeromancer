"""SQLite storage for the timeseries.

One row per measurement; the recorder writes and the dashboard reads
concurrently, which WAL mode makes safe across processes.
"""

from __future__ import annotations

import math
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .device import Reading

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    ts       REAL NOT NULL,  -- unix time, seconds
    quantity TEXT NOT NULL,  -- co2 | temperature | humidity | op_XX (undocumented codes) | blueair_<sensor> | nea_pm25_<region> | nea_<weather>_<station>
             -- | synop_<field>_<WMO id> | metar_<field>_<ICAO id> | home_pressure[_msl] | health_<field> (a wearable)
    value    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS readings_quantity_ts ON readings (quantity, ts);
CREATE TABLE IF NOT EXISTS placements (
    id     INTEGER PRIMARY KEY,
    ts     REAL NOT NULL,  -- unix time the device got here; 0 = since before recording began
    device TEXT NOT NULL,  -- see DEVICES
    room   TEXT NOT NULL,
    spot   TEXT NOT NULL   -- free text: where in the room, height, what is nearby
);
CREATE TABLE IF NOT EXISTS stations (  -- outdoor weather stations, as nea_<kind>_<id> and metar_<field>_<id> name them
    id        TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    latitude  REAL NOT NULL,
    longitude REAL NOT NULL,
    elevation REAL  -- metres above mean sea level, where known
);
CREATE TABLE IF NOT EXISTS tokens (  -- who may read the hosted dashboard or upload to it (tokens.py)
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL,
    scope   TEXT NOT NULL,         -- view | write
    hash    TEXT NOT NULL UNIQUE,  -- SHA-256 of the secret, hex; the secret itself is never stored
    created REAL NOT NULL,
    expires REAL,                  -- unix time; NULL = never
    revoked REAL
);
CREATE TABLE IF NOT EXISTS pushed (  -- how far the meter's readings have been uploaded to each server (push.py)
    url        TEXT PRIMARY KEY,
    last_rowid INTEGER NOT NULL
);
"""

QUANTITIES = ("co2", "temperature", "humidity")
DEVICES = ("zytemp", "blueair")


def device_of(quantity: str) -> str | None:
    """The device that measured ``quantity``; None for outdoor data and the wearable, which have no placement."""
    if quantity.startswith(("nea_", "synop_", "metar_", "home_", "health_")):
        return None
    return "blueair" if quantity.startswith("blueair_") else "zytemp"


def is_meter(quantity: str) -> bool:
    """Whether the meter itself measures ``quantity``: what recording machines upload (push.py)."""
    return quantity in QUANTITIES or quantity.startswith("op_")


@dataclass(frozen=True)
class Placement:
    id: int
    ts: float
    device: str
    room: str
    spot: str


def default_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"))
    return base / "aeromancer" / "readings.sqlite3"


class Store:
    """Not thread-safe: open one Store per thread.

    A ``readonly`` Store opens an existing database through SQLite's ``mode=ro``, which refuses every
    write, and leaves the schema and journal mode to whoever records into it.
    """

    def __init__(self, path: str | os.PathLike, readonly: bool = False):
        if readonly:
            if not Path(path).exists():
                raise FileNotFoundError(f"no database at {path}; record into it first")
            self.db = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True, timeout=10)
            # SQLite opens the WAL read-write even so; never checkpoint it on close (Python 3.12+), and leave that
            # to the recorder. Readers still update the -shm index, which is how WAL readers coordinate.
            if hasattr(self.db, "setconfig"):
                self.db.setconfig(sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE, True)
            return
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        if "elevation" not in {row[1] for row in self.db.execute("PRAGMA table_info(stations)")}:
            self.db.execute("ALTER TABLE stations ADD COLUMN elevation REAL")  # added after the first version

    def close(self) -> None:
        self.db.close()

    def add(self, readings: Iterable[Reading]) -> None:
        with self.db:
            self.db.executemany(
                "INSERT INTO readings (ts, quantity, value) VALUES (?, ?, ?)",
                ((r.ts, r.quantity, r.value) for r in readings),
            )

    def add_new(self, readings: Iterable[Reading]) -> int:
        """Add the readings not stored yet (by quantity and time), so uploads can be retried; returns how many were new."""
        with self.db:
            before = self.db.total_changes
            self.db.executemany(
                "INSERT INTO readings (ts, quantity, value) SELECT ?1, ?2, ?3"
                " WHERE NOT EXISTS (SELECT 1 FROM readings WHERE quantity = ?2 AND ts = ?1)",
                ((r.ts, r.quantity, r.value) for r in readings),
            )
            return self.db.total_changes - before

    def unpushed(self, after_rowid: int, limit: int) -> list[tuple[int, float, str, float]]:
        """``(rowid, ts, quantity, value)`` of the meter's readings stored after ``after_rowid``, oldest first."""
        return self.db.execute(
            "SELECT rowid, ts, quantity, value FROM readings"
            " WHERE rowid > ? AND (quantity IN (?, ?, ?) OR quantity GLOB 'op_*') ORDER BY rowid LIMIT ?",
            (after_rowid, *QUANTITIES, limit),
        ).fetchall()

    def push_cursor(self, url: str) -> int:
        row = self.db.execute("SELECT last_rowid FROM pushed WHERE url = ?", (url,)).fetchone()
        return row[0] if row else 0

    def set_push_cursor(self, url: str, rowid: int) -> None:
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO pushed (url, last_rowid) VALUES (?, ?)", (url, rowid))

    def add_stations(self, stations: Iterable[tuple]) -> None:
        """``(id, name, latitude, longitude[, elevation])``, replacing what was known of each."""
        with self.db:
            self.db.executemany(
                "INSERT OR REPLACE INTO stations (id, name, latitude, longitude, elevation) VALUES (?, ?, ?, ?, ?)",
                ((*s, None)[:5] for s in stations),
            )

    def stations(self) -> dict[str, tuple[float, float]]:
        """Each station's ``(latitude, longitude)``."""
        return {i: (lat, lon) for i, lat, lon in self.db.execute("SELECT id, latitude, longitude FROM stations")}

    def elevations(self) -> dict[str, float]:
        """Each station's elevation, of those whose elevation is known."""
        return dict(self.db.execute("SELECT id, elevation FROM stations WHERE elevation IS NOT NULL"))

    def span(self) -> tuple[float, float] | None:
        first, last = self.db.execute("SELECT MIN(ts), MAX(ts) FROM readings").fetchone()
        return None if first is None else (first, last)

    def last_ts(self, pattern: str) -> float | None:
        """Time of the newest reading of any quantity matching the GLOB ``pattern``."""
        return self.db.execute("SELECT MAX(ts) FROM readings WHERE quantity GLOB ?", (pattern,)).fetchone()[0]

    def first_ts(self, pattern: str) -> float | None:
        """Time of the oldest reading of any quantity matching the GLOB ``pattern``."""
        return self.db.execute("SELECT MIN(ts) FROM readings WHERE quantity GLOB ?", (pattern,)).fetchone()[0]

    def rows(self, pattern: str, start: float, end: float) -> list[tuple[float, str, float]]:
        """``(ts, quantity, value)`` of every reading of the quantities matching the GLOB ``pattern``, from ``start`` to ``end``."""
        return self.db.execute(
            "SELECT ts, quantity, value FROM readings WHERE quantity GLOB ? AND ts >= ? AND ts <= ? ORDER BY ts",
            (pattern, start, end),
        ).fetchall()

    def replace(self, pattern: str, start: float, end: float, readings: Iterable[Reading]) -> None:
        """Delete the readings of the quantities matching ``pattern`` from ``start`` to ``end``, and add ``readings``, at once."""
        with self.db:
            self.db.execute("DELETE FROM readings WHERE quantity GLOB ? AND ts >= ? AND ts <= ?", (pattern, start, end))
            self.db.executemany(
                "INSERT INTO readings (ts, quantity, value) VALUES (?, ?, ?)", ((r.ts, r.quantity, r.value) for r in readings)
            )

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM readings").fetchone()[0]

    def signal_names(self) -> list[str]:
        """The undocumented ``op_XX`` quantities ever recorded (skip-scans the index)."""
        rows = self.db.execute(
            """
            WITH RECURSIVE q(name) AS (
                SELECT MIN(quantity) FROM readings
                UNION ALL
                SELECT (SELECT MIN(quantity) FROM readings WHERE quantity > q.name) FROM q WHERE q.name IS NOT NULL
            )
            SELECT name FROM q WHERE name GLOB 'op_*'
            """
        ).fetchall()
        return [name for (name,) in rows]

    def latest_of(self, quantity: str, before: float = math.inf) -> tuple[float, float] | None:
        """``(ts, value)`` of the newest reading of ``quantity``, or of the newest before ``before``."""
        return self.db.execute(
            "SELECT ts, value FROM readings WHERE quantity = ? AND ts < ? ORDER BY ts DESC LIMIT 1", (quantity, before)
        ).fetchone()

    def latest(self) -> dict[str, tuple[float, float]]:
        out = {}
        for q in QUANTITIES:
            row = self.db.execute(
                "SELECT ts, value FROM readings WHERE quantity = ? ORDER BY ts DESC LIMIT 1", (q,)
            ).fetchone()
            if row:
                out[q] = row
        return out

    def series(
        self, quantity: str, start: float, end: float, bucket: float, lead: bool = False
    ) -> list[tuple[float, float, float, float]]:
        """``(mean ts, mean, min, max)`` per ``bucket``-second interval, in time order.

        With ``lead``, a series with readings in the window starts with the last reading before
        it, so that a chart can draw its line from the window's edge.
        """
        rows = self.db.execute(
            """
            SELECT AVG(ts), AVG(value), MIN(value), MAX(value)
            FROM readings
            WHERE quantity = ? AND ts >= ? AND ts <= ?
            GROUP BY CAST(ts / ? AS INTEGER)
            ORDER BY 1
            """,
            (quantity, start, end, bucket),
        ).fetchall()
        if lead and rows and (before := self.latest_of(quantity, before=start)):
            rows.insert(0, (before[0], before[1], before[1], before[1]))
        return rows

    def place(self, ts: float, device: str, room: str, spot: str = "") -> int:
        """Record that ``device`` is in ``room`` at ``spot`` from ``ts`` on; returns the record's id."""
        if device not in DEVICES:
            raise ValueError(f"unknown device {device!r}; expected one of {', '.join(DEVICES)}")
        with self.db:
            return self.db.execute(
                "INSERT INTO placements (ts, device, room, spot) VALUES (?, ?, ?, ?)", (ts, device, room, spot)
            ).lastrowid

    def unplace(self, id: int) -> bool:
        with self.db:
            return self.db.execute("DELETE FROM placements WHERE id = ?", (id,)).rowcount > 0

    def placements(self, device: str | None = None) -> list[Placement]:
        """Every placement, in time order; of one time, the one recorded last wins and comes last."""
        rows = self.db.execute(
            "SELECT id, ts, device, room, spot FROM placements WHERE ?1 IS NULL OR device = ?1 ORDER BY ts, id",
            (device,),
        ).fetchall()
        return [Placement(*row) for row in rows]

    def placement_at(self, device: str, ts: float) -> Placement | None:
        """Where ``device`` was at ``ts``, or None if nobody recorded it."""
        row = self.db.execute(
            "SELECT id, ts, device, room, spot FROM placements WHERE device = ? AND ts <= ? ORDER BY ts DESC, id DESC LIMIT 1",
            (device, ts),
        ).fetchone()
        return Placement(*row) if row else None
