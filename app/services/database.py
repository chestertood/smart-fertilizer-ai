"""SQLite logging for sensor readings and dosing events.

Stdlib-only (sqlite3). The readings table is the foundation a future ML model
will train on. The dosing_events table records every dispense (manual or
LLM-approved) for the History view and for auditing.
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Project-root/data/fertilizer.db. When frozen by `flet pack`, __file__ is in
# the temp _MEIPASS dir (wiped on exit) — write the DB next to the exe instead
# so logged history survives a restart.
if getattr(sys, "frozen", False):
    _DEFAULT_DIR = os.path.join(os.path.dirname(sys.executable), "data")
else:
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
                humidity  REAL,
                stage     TEXT
            );
            CREATE TABLE IF NOT EXISTS dosing_events (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ts      TEXT NOT NULL,
                pump    TEXT NOT NULL,
                amount  REAL NOT NULL,
                source  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS llm_usage (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                ts             TEXT NOT NULL,
                model          TEXT NOT NULL,
                input_tokens   INTEGER NOT NULL,
                output_tokens  INTEGER NOT NULL
            );
            """
        )
        # Migration for DBs created before the stage column existed —
        # growth-stage context is training data for the future ML model.
        cols = [r[1] for r in self._conn.execute("PRAGMA table_info(readings)")]
        if "stage" not in cols:
            self._conn.execute("ALTER TABLE readings ADD COLUMN stage TEXT")
        self._conn.commit()

    # -- readings -----------------------------------------------------------

    def log_reading(self, readings: dict, stage: str | None = None) -> None:
        """Persist one sensor snapshot. Keys: EC, PH, Temperature, Humidity.
        Missing/NaN values are stored as NULL. `stage` = current growth-stage
        name if a grow cycle is being tracked (context for future ML)."""
        def clean(v):
            try:
                v = float(v)
                return v if v == v else None  # drop NaN
            except (TypeError, ValueError):
                return None

        self._conn.execute(
            "INSERT INTO readings (ts, ec, ph, temp, humidity, stage) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                _now(),
                clean(readings.get("EC")),
                clean(readings.get("PH")),
                clean(readings.get("Temperature")),
                clean(readings.get("Humidity")),
                stage,
            ),
        )
        self._conn.commit()

    def recent_readings(self, limit: int = 100) -> list[sqlite3.Row]:
        """Most-recent-first list of reading rows."""
        cur = self._conn.execute(
            "SELECT ts, ec, ph, temp, humidity, stage FROM readings "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()

    def readings_since(self, since_iso: str) -> list[sqlite3.Row]:
        """Oldest-first reading rows since an ISO UTC timestamp — feeds the
        History time-series charts."""
        cur = self._conn.execute(
            "SELECT ts, ec, ph, temp, humidity FROM readings "
            "WHERE ts >= ? ORDER BY id ASC",
            (since_iso,),
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

    # -- LLM usage ------------------------------------------------------------
    # Local token ledger. The regular API key cannot query Anthropic billing
    # (that needs an org admin key), so the Settings page estimates cost from
    # what this app itself has spent.

    def log_llm_usage(self, model: str, input_tokens: int, output_tokens: int) -> None:
        """Record token usage of one Claude API call."""
        self._conn.execute(
            "INSERT INTO llm_usage (ts, model, input_tokens, output_tokens) "
            "VALUES (?, ?, ?, ?)",
            (_now(), model, int(input_tokens), int(output_tokens)),
        )
        self._conn.commit()

    def llm_usage_by_model(self, since: str | None = None) -> list[dict]:
        """Per-model token totals, optionally since an ISO timestamp (UTC —
        same clock as the ts column). Rows: {"model","calls","input","output"}."""
        sql = ("SELECT model, COUNT(*) AS calls, "
               "COALESCE(SUM(input_tokens),0) AS input, "
               "COALESCE(SUM(output_tokens),0) AS output FROM llm_usage")
        args: tuple = ()
        if since is not None:
            sql += " WHERE ts >= ?"
            args = (since,)
        sql += " GROUP BY model ORDER BY input + output DESC"
        return [dict(r) for r in self._conn.execute(sql, args)]

    def llm_usage_summary(self) -> dict:
        """Per-model usage for today / this month / all time (UTC periods).
        Feeds the Settings page cost estimate."""
        now = datetime.now(timezone.utc)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)
        return {
            "today": self.llm_usage_by_model(day_start.isoformat(timespec="seconds")),
            "month": self.llm_usage_by_model(month_start.isoformat(timespec="seconds")),
            "all": self.llm_usage_by_model(None),
        }

    def close(self) -> None:
        self._conn.close()
