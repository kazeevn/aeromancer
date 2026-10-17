"""SQLite storage for the timeseries.

One row per measurement; the recorder writes and the dashboard reads
concurrently, which WAL mode makes safe across processes.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable

from .device import Reading

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    ts       REAL NOT NULL,  -- unix time, seconds
    quantity TEXT NOT NULL,  -- co2 | temperature | humidity | op_XX (undocumented codes) | blueair_<sensor>
    value    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS readings_quantity_ts ON readings (quantity, ts);
"""

QUANTITIES = ("co2", "temperature", "humidity")


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

    def span(self) -> tuple[float, float] | None:
        first, last = self.db.execute("SELECT MIN(ts), MAX(ts) FROM readings").fetchone()
        return None if first is None else (first, last)

    def last_ts(self, pattern: str) -> float | None:
        """Time of the newest reading of any quantity matching the GLOB ``pattern``."""
        return self.db.execute("SELECT MAX(ts) FROM readings WHERE quantity GLOB ?", (pattern,)).fetchone()[0]

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
