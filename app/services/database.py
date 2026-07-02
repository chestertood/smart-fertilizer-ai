"""SQLite logging for sensor readings and dosing events.

Stdlib-only (sqlite3). The readings table is the foundation a future ML model
will train on. The dosing_events table records every dispense (manual or
LLM-approved) for the History view and for auditing.
"""

import os
import sqlite3
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Project-root/data/fertilizer.db
_DEFAULT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """Thin wrapper around a SQLite connection. One instance per app."""

    def __init__(self, path: str | None = None):
        if path is None:
            os.makedirs(_DEFAULT_DIR, exist_ok=True)
            path = os.path.join(_DEFAULT_DIR, "fertilizer.db")
        # check_same_thread=False: the connectivity/poll tasks may touch it
        # from executor threads. Writes are tiny and serialized by SQLite.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        logger.info("Database ready at %s", path)

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS readings (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        TEXT NOT NULL,
                ec        REAL,
                ph        REAL,
                temp      REAL,
                humidity  REAL
            );
            CREATE TABLE IF NOT EXISTS dosing_events (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ts      TEXT NOT NULL,
                pump    TEXT NOT NULL,
                amount  REAL NOT NULL,
                source  TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    # -- readings -----------------------------------------------------------

    def log_reading(self, readings: dict) -> None:
        """Persist one sensor snapshot. Keys: EC, PH, Temperature, Humidity.
        Missing/NaN values are stored as NULL."""
        def clean(v):
            try:
                v = float(v)
                return v if v == v else None  # drop NaN
            except (TypeError, ValueError):
                return None

        self._conn.execute(
            "INSERT INTO readings (ts, ec, ph, temp, humidity) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                _now(),
                clean(readings.get("EC")),
                clean(readings.get("PH")),
                clean(readings.get("Temperature")),
                clean(readings.get("Humidity")),
            ),
        )
        self._conn.commit()

    def recent_readings(self, limit: int = 100) -> list[sqlite3.Row]:
        """Most-recent-first list of reading rows."""
        cur = self._conn.execute(
            "SELECT ts, ec, ph, temp, humidity FROM readings "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()

    # -- dosing -------------------------------------------------------------

    def log_dose(self, pump: str, amount: float, source: str) -> None:
        """Record a dispense. `source` is 'manual' or 'llm'."""
        self._conn.execute(
            "INSERT INTO dosing_events (ts, pump, amount, source) "
            "VALUES (?, ?, ?, ?)",
            (_now(), pump, float(amount), source),
        )
        self._conn.commit()

    def recent_doses(self, limit: int = 50) -> list[sqlite3.Row]:
        """Most-recent-first list of dosing events."""
        cur = self._conn.execute(
            "SELECT ts, pump, amount, source FROM dosing_events "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()

    def close(self) -> None:
        self._conn.close()
