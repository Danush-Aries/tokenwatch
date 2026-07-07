"""SQLite-backed store for recorded LLM requests.

Uses only the stdlib ``sqlite3`` module and parameterized queries. A module-level
database path is set by :func:`init_db` so the FastAPI app and tests can point at
different files.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Optional

_DB_PATH: str = "tokenwatch.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                REAL    NOT NULL,
    model             TEXT    NOT NULL,
    prompt_tokens     INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    total_tokens      INTEGER NOT NULL,
    cost_usd          REAL    NOT NULL,
    latency_ms        REAL    NOT NULL,
    status            INTEGER NOT NULL
);
"""


def _connect(path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or _DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str) -> None:
    """Set the active database path and create the schema if needed."""
    global _DB_PATH
    _DB_PATH = path
    with _connect(path) as conn:
        conn.execute(_SCHEMA)
        conn.commit()


def record(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    latency_ms: float,
    status: int,
    ts: Optional[float] = None,
) -> int:
    """Insert a request row and return its new id."""
    total_tokens = prompt_tokens + completion_tokens
    ts = time.time() if ts is None else ts
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO requests
                (ts, model, prompt_tokens, completion_tokens, total_tokens,
                 cost_usd, latency_ms, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                model,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                cost_usd,
                latency_ms,
                status,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def summary() -> dict:
    """Return aggregate spend, token count, and request count."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(cost_usd), 0.0)     AS total_cost,
                COALESCE(SUM(total_tokens), 0)   AS total_tokens,
                COUNT(*)                         AS count
            FROM requests
            """
        ).fetchone()
    return {
        "total_cost_usd": row["total_cost"],
        "total_tokens": row["total_tokens"],
        "count": row["count"],
    }


def by_model() -> list[dict]:
    """Return per-model aggregates ordered by spend descending."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                model,
                COUNT(*)                       AS count,
                SUM(total_tokens)              AS total_tokens,
                SUM(cost_usd)                  AS cost_usd
            FROM requests
            GROUP BY model
            ORDER BY cost_usd DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def by_day() -> list[dict]:
    """Return per-day aggregates (UTC calendar day) ordered oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                date(ts, 'unixepoch')          AS day,
                COUNT(*)                       AS count,
                SUM(total_tokens)              AS total_tokens,
                SUM(cost_usd)                  AS cost_usd
            FROM requests
            GROUP BY day
            ORDER BY day ASC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def recent(limit: int = 50) -> list[dict]:
    """Return the most recent request rows, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, ts, model, prompt_tokens, completion_tokens,
                   total_tokens, cost_usd, latency_ms, status
            FROM requests
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
