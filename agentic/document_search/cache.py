"""
SQLite Cache (Persistent Document Index)
=========================================

Manages a SQLite database at ``data/document_index.db`` that stores
all indexed file metadata and embeddings.

Schema
------
files
    - path           TEXT PRIMARY KEY
    - filename       TEXT
    - extension      TEXT
    - size_bytes     INTEGER
    - modified_ts    REAL
    - folder         TEXT
    - folder_path    TEXT
    - sample_text    TEXT
    - keywords       TEXT
    - summary        TEXT
    - embedding      BLOB   (raw float32 bytes)
    - indexed_at     REAL   (Unix timestamp of when we indexed it)

index_meta
    - key            TEXT PRIMARY KEY
    - value          TEXT
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from typing import List, Optional

from agentic.document_search.schemas import IndexedFile

logger = logging.getLogger(__name__)

# ── Database location ──────────────────────────────────────────────────────
_DB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)
DB_PATH = os.path.join(_DB_DIR, "document_index.db")

# Thread-local connections for thread safety
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Return a per-thread SQLite connection, creating it if needed."""
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(_DB_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-8000")  # 8 MB page cache
        _local.conn = conn
    return _local.conn


def init_db() -> None:
    """Create tables if they do not exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS files (
            path        TEXT PRIMARY KEY,
            filename    TEXT NOT NULL,
            extension   TEXT NOT NULL,
            size_bytes  INTEGER DEFAULT 0,
            modified_ts REAL DEFAULT 0,
            folder      TEXT DEFAULT '',
            folder_path TEXT DEFAULT '',
            sample_text TEXT DEFAULT '',
            keywords    TEXT DEFAULT '',
            summary     TEXT DEFAULT '',
            embedding   BLOB,
            indexed_at  REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS index_meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension);
        CREATE INDEX IF NOT EXISTS idx_files_modified  ON files(modified_ts);
        CREATE INDEX IF NOT EXISTS idx_files_folder    ON files(folder_path);
    """)
    conn.commit()
    logger.debug("[CACHE] Database initialised at %s", DB_PATH)


def upsert_file(f: IndexedFile) -> None:
    """Insert or replace a file record in the database."""
    conn = _get_conn()
    conn.execute(
        """
        INSERT OR REPLACE INTO files
            (path, filename, extension, size_bytes, modified_ts,
             folder, folder_path, sample_text, keywords, summary,
             embedding, indexed_at)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f.path, f.filename, f.extension, f.size_bytes, f.modified_ts,
            f.folder, f.folder_path, f.sample_text, f.keywords, f.summary,
            f.embedding_blob, time.time(),
        ),
    )
    conn.commit()


def get_file_by_path(path: str) -> Optional[IndexedFile]:
    """Retrieve a single file record by its absolute path."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT path, filename, extension, size_bytes, modified_ts, "
        "folder, folder_path, sample_text, keywords, summary, embedding "
        "FROM files WHERE path = ?",
        (path,),
    ).fetchone()
    if row is None:
        return None
    return IndexedFile(
        path=row[0], filename=row[1], extension=row[2],
        size_bytes=row[3], modified_ts=row[4],
        folder=row[5], folder_path=row[6],
        sample_text=row[7], keywords=row[8], summary=row[9],
        embedding_blob=row[10],
    )


def get_all_files(with_embeddings: bool = True) -> List[IndexedFile]:
    """Return all indexed files.

    Parameters
    ----------
    with_embeddings:
        If False, the ``embedding_blob`` field is not loaded (faster for
        pure metadata queries).
    """
    conn = _get_conn()
    if with_embeddings:
        query = (
            "SELECT path, filename, extension, size_bytes, modified_ts, "
            "folder, folder_path, sample_text, keywords, summary, embedding "
            "FROM files"
        )
    else:
        query = (
            "SELECT path, filename, extension, size_bytes, modified_ts, "
            "folder, folder_path, sample_text, keywords, summary, NULL "
            "FROM files"
        )

    rows = conn.execute(query).fetchall()
    results: List[IndexedFile] = []
    for row in rows:
        results.append(IndexedFile(
            path=row[0], filename=row[1], extension=row[2],
            size_bytes=row[3], modified_ts=row[4],
            folder=row[5], folder_path=row[6],
            sample_text=row[7], keywords=row[8], summary=row[9],
            embedding_blob=row[10],
        ))
    return results


def delete_file(path: str) -> None:
    """Remove a file record (called when the file no longer exists on disk)."""
    conn = _get_conn()
    conn.execute("DELETE FROM files WHERE path = ?", (path,))
    conn.commit()


def get_last_scan_time() -> float:
    """Return the Unix timestamp of the last completed full scan, or 0."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT value FROM index_meta WHERE key = 'last_full_scan'"
    ).fetchone()
    if row is None:
        return 0.0
    try:
        return float(row[0])
    except (ValueError, TypeError):
        return 0.0


def set_last_scan_time(ts: float) -> None:
    """Record the timestamp of the most recent completed full scan."""
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO index_meta (key, value) VALUES ('last_full_scan', ?)",
        (str(ts),),
    )
    conn.commit()


def get_indexed_count() -> int:
    """Return the total number of files in the index."""
    conn = _get_conn()
    row = conn.execute("SELECT COUNT(*) FROM files").fetchone()
    return row[0] if row else 0


def get_files_needing_reindex(since_ts: float) -> List[str]:
    """Return paths of files whose ``indexed_at`` is older than ``since_ts``."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT path FROM files WHERE indexed_at < ?", (since_ts,)
    ).fetchall()
    return [r[0] for r in rows]
