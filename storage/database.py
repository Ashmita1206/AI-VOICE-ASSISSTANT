"""
SQLite Database Layer
=====================

Manages the SQLite connection, table creation, and raw CRUD
operations for the session history.
"""

import os
import sqlite3
import logging
from typing import Any

import config

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(config.BASE_DIR, "data")
DB_PATH = os.path.join(DB_DIR, "history.db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    input_type      TEXT DEFAULT 'audio',
    audio_filename  TEXT,
    transcript      TEXT,
    language        TEXT,
    stt_confidence  REAL DEFAULT 0.0,
    wer_accuracy    REAL DEFAULT 0.0,
    intent          TEXT,
    entities        TEXT,
    planner_output  TEXT,
    execution_logs  TEXT,
    response_text   TEXT,
    tts_audio_path  TEXT
);
"""

# ── Connection helper ────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    """Return a new connection with row-factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the data directory and sessions table if they don't exist."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = _get_conn()
    try:
        conn.execute(_CREATE_TABLE)
        conn.commit()
        logger.info("Database initialised at %s", DB_PATH)
    finally:
        conn.close()


# ── CRUD ─────────────────────────────────────────────────────────────

def insert_session(entry: dict[str, Any]) -> None:
    """Insert a single session row."""
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO sessions
               (id, timestamp, input_type, audio_filename, transcript,
                language, stt_confidence, wer_accuracy, intent,
                entities, planner_output, execution_logs,
                response_text, tts_audio_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry["id"],
                entry["timestamp"],
                entry.get("input_type", "audio"),
                entry.get("audio_filename", ""),
                entry.get("transcript", ""),
                entry.get("language", ""),
                entry.get("stt_confidence", 0.0),
                entry.get("wer_accuracy", 0.0),
                entry.get("intent", ""),
                entry.get("entities", "{}"),
                entry.get("planner_output", "{}"),
                entry.get("execution_logs", "[]"),
                entry.get("response_text", ""),
                entry.get("tts_audio_path", ""),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_session(session_id: str) -> dict[str, Any] | None:
    """Retrieve a single session by ID."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_sessions() -> list[dict[str, Any]]:
    """Retrieve all sessions, newest first."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY timestamp DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_session(session_id: str) -> bool:
    """Delete a session by ID. Returns True if a row was deleted."""
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "DELETE FROM sessions WHERE id = ?", (session_id,)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
