"""SQLite storage for the timeseries.

One row per measurement; the recorder writes and the dashboard reads
concurrently, which WAL mode makes safe across processes.
"""

from __future__ import annotations

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
CREATE TABLE IF NOT EXISTS stations (  -- outdoor weather stations, as nea_<kind>_<id> names them
    id        TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    latitude  REAL NOT NULL,
    longitude REAL NOT NULL
);
"""

QUANTITIES = ("co2", "temperature", "humidity")
DEVICES = ("zytemp", "blueair")


def device_of(quantity: str) -> str | None:
    """The device that measured ``quantity``; None for outdoor data, which has no placement."""
    if quantity.startswith("nea_"):
        return None
    return "blueair" if quantity.startswith("blueair_") else "zytemp"


@dataclass(frozen=True)
class Placement:
    id: int
    ts: float
    device: str
    room: str
    spot: str


def default_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"))
    path = base / "aeromancer" / "readings.sqlite3"
    legacy = base / "co2monitor" / "readings.sqlite3"  # from before the project was renamed
    return legacy if legacy.exists() and not path.exists() else path


class Store:
    """Not thread-safe: open one Store per thread."""

    def __init__(self, path: str | os.PathLike):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def add(self, readings: Iterable[Reading]) -> None:
        with self.db:
            self.db.executemany(
                "INSERT INTO readings (ts, quantity, value) VALUES (?, ?, ?)",
                ((r.ts, r.quantity, r.value) for r in readings),
            )

    def add_stations(self, stations: Iterable[tuple[str, str, float, float]]) -> None:
        """``(id, name, latitude, longitude)``, replacing what was known of each."""
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO stations (id, name, latitude, longitude) VALUES (?, ?, ?, ?)", stations)

    def stations(self) -> dict[str, tuple[float, float]]:
        """Each station's ``(latitude, longitude)``."""
        return {i: (lat, lon) for i, lat, lon in self.db.execute("SELECT id, latitude, longitude FROM stations")}

    def span(self) -> tuple[float, float] | None:
        first, last = self.db.execute("SELECT MIN(ts), MAX(ts) FROM readings").fetchone()
        return None if first is None else (first, last)

    def last_ts(self, pattern: str) -> float | None:
        """Time of the newest reading of any quantity matching the GLOB ``pattern``."""
        return self.db.execute("SELECT MAX(ts) FROM readings WHERE quantity GLOB ?", (pattern,)).fetchone()[0]

    def first_ts(self, pattern: str) -> float | None:
        """Time of the oldest reading of any quantity matching the GLOB ``pattern``."""
        return self.db.execute("SELECT MIN(ts) FROM readings WHERE quantity GLOB ?", (pattern,)).fetchone()[0]

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
        self, quantity: str, start: float, end: float, bucket: float
    ) -> list[tuple[float, float, float, float]]:
        """``(mean ts, mean, min, max)`` per ``bucket``-second interval, in time order."""
        return self.db.execute(
            """
            SELECT AVG(ts), AVG(value), MIN(value), MAX(value)
            FROM readings
            WHERE quantity = ? AND ts >= ? AND ts <= ?
            GROUP BY CAST(ts / ? AS INTEGER)
            ORDER BY 1
            """,
            (quantity, start, end, bucket),
        ).fetchall()

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
