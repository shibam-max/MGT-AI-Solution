from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

from src.tracing import iso8601_utc


DB_PATH = os.environ.get("AGENT_DB", "agent_state.db")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                trace_id TEXT PRIMARY KEY,
                document_id TEXT,
                status TEXT,
                confidence REAL,
                branch TEXT,
                sor_id TEXT,
                created_at TEXT,
                payload TEXT
            );

            CREATE TABLE IF NOT EXISTS stage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT,
                name TEXT,
                status TEXT,
                latency_ms INTEGER,
                summary TEXT,
                ts TEXT,
                FOREIGN KEY(trace_id) REFERENCES runs(trace_id)
            );

            CREATE TABLE IF NOT EXISTS artifacts (
                trace_id TEXT PRIMARY KEY,
                artifact TEXT,
                FOREIGN KEY(trace_id) REFERENCES runs(trace_id)
            );

            CREATE TABLE IF NOT EXISTS dead_letter (
                trace_id TEXT PRIMARY KEY,
                reason TEXT,
                payload TEXT,
                created_at TEXT
            );
            """
        )
        conn.commit()


def save_run(result: dict) -> None:
    trace_id = result["trace_id"]
    decision = result.get("decision") or {}
    log = result.get("log") or []
    artifact = result.get("artifact") or {}

    with connect() as conn:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    trace_id,
                    document_id,
                    status,
                    confidence,
                    branch,
                    sor_id,
                    created_at,
                    payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    result.get("document_id"),
                    result.get("status"),
                    result.get("confidence"),
                    decision.get("branch"),
                    decision.get("sor_id"),
                    result.get("started_at"),
                    json.dumps(result),
                ),
            )
            conn.execute("DELETE FROM stage_events WHERE trace_id = ?", (trace_id,))
            conn.executemany(
                """
                INSERT INTO stage_events (
                    trace_id,
                    name,
                    status,
                    latency_ms,
                    summary,
                    ts
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        trace_id,
                        event.get("name"),
                        event.get("status"),
                        event.get("latency_ms"),
                        _json_or_text(event.get("summary")),
                        event.get("ts"),
                    )
                    for event in log
                ],
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO artifacts (trace_id, artifact)
                VALUES (?, ?)
                """,
                (trace_id, json.dumps(artifact)),
            )


def dead_letter(trace_id, reason, payload, ts=None) -> None:
    created_at = ts or iso8601_utc()
    with connect() as conn:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO dead_letter (
                    trace_id,
                    reason,
                    payload,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (trace_id, reason, json.dumps(payload), created_at),
            )


def get_run(trace_id) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute(
            "SELECT payload FROM runs WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()

    if row is None:
        return None
    return json.loads(row["payload"])


def get_events(trace_id) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT trace_id, name, status, latency_ms, summary, ts
            FROM stage_events
            WHERE trace_id = ?
            ORDER BY id
            """,
            (trace_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_runs(limit=50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT trace_id, document_id, status, confidence, branch, sor_id, created_at
            FROM runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_dead_letter() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT trace_id, reason, payload, created_at
            FROM dead_letter
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def replay_dead_letter(trace_id) -> Optional[dict]:
    with connect() as conn:
        row = conn.execute(
            "SELECT payload FROM dead_letter WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()

    if row is None:
        return None
    return json.loads(row["payload"])


def _json_or_text(value) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value)
