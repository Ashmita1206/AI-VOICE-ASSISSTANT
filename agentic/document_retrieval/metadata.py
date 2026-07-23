"""
Document Retrieval Metadata Database
====================================

SQLite layer for document metadata (no vector BLOBs).
"""

import logging
import os
import sqlite3
import threading
import time
from typing import List, Optional, Tuple

from agentic.document_retrieval import config
from agentic.document_retrieval.schemas import IndexedDocument

logger = logging.getLogger(__name__)

_local = threading.local()

def reset_db_connection() -> None:
    if hasattr(_local, "conn") and _local.conn is not None:
        try:
            _local.conn.close()
        except Exception:
            pass
        _local.conn = None

def _get_conn() -> sqlite3.Connection:
    current_db = getattr(_local, "db_path", None)
    if not hasattr(_local, "conn") or _local.conn is None or current_db != config.SQLITE_DB_PATH:
        reset_db_connection()
        os.makedirs(os.path.dirname(config.SQLITE_DB_PATH), exist_ok=True)
        conn = sqlite3.connect(config.SQLITE_DB_PATH, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
        _local.db_path = config.SQLITE_DB_PATH
    return _local.conn

def init_db() -> None:
    """Create the metadata tables and perform schema migration if needed."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS docs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            path           TEXT UNIQUE NOT NULL,
            filename       TEXT NOT NULL,
            folder         TEXT DEFAULT '',
            parent_folder  TEXT DEFAULT '',
            project_folder TEXT DEFAULT '',
            relative_path  TEXT DEFAULT '',
            extension      TEXT NOT NULL,
            size_bytes     INTEGER DEFAULT 0,
            modified_ts    REAL DEFAULT 0,
            summary        TEXT DEFAULT '',
            entities       TEXT DEFAULT '{}',
            keywords       TEXT DEFAULT '',
            content_hash   TEXT DEFAULT '',
            last_indexed   REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_docs_extension      ON docs(extension);
        CREATE INDEX IF NOT EXISTS idx_docs_modified       ON docs(modified_ts);
        CREATE INDEX IF NOT EXISTS idx_docs_folder         ON docs(folder);
    """)
    
    # Auto-migration: ensure parent_folder, project_folder, relative_path columns exist for older DBs
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(docs)").fetchall()}
    for col, col_type in [("parent_folder", "TEXT DEFAULT ''"), ("project_folder", "TEXT DEFAULT ''"), ("relative_path", "TEXT DEFAULT ''")]:
        if col not in existing_cols:
            try:
                conn.execute(f"ALTER TABLE docs ADD COLUMN {col} {col_type}")
            except Exception as e:
                logger.debug(f"Migration column add error for {col}: {e}")

    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_docs_parent_folder  ON docs(parent_folder);
        CREATE INDEX IF NOT EXISTS idx_docs_project_folder ON docs(project_folder);
    """)
    conn.commit()

def upsert_document(doc: IndexedDocument) -> int:
    """Insert or replace a document, returning its ID."""
    conn = _get_conn()
    
    # Ensure parent_folder & project_folder defaults
    parent_folder = getattr(doc, 'parent_folder', '') or doc.folder
    project_folder = getattr(doc, 'project_folder', '') or doc.folder
    relative_path = getattr(doc, 'relative_path', '') or doc.filename

    existing = conn.execute("SELECT id FROM docs WHERE path = ?", (doc.path,)).fetchone()
    
    if existing:
        doc_id = existing[0]
        conn.execute(
            """
            UPDATE docs SET
                filename=?, folder=?, parent_folder=?, project_folder=?, relative_path=?,
                extension=?, size_bytes=?, modified_ts=?, summary=?, entities=?,
                keywords=?, content_hash=?, last_indexed=?
            WHERE id = ?
            """,
            (doc.filename, doc.folder, parent_folder, project_folder, relative_path,
             doc.extension, doc.size_bytes, doc.modified_ts, doc.summary, doc.entities_json,
             doc.keywords, doc.content_hash, time.time(), doc_id)
        )
    else:
        cursor = conn.execute(
            """
            INSERT INTO docs
                (path, filename, folder, parent_folder, project_folder, relative_path,
                 extension, size_bytes, modified_ts, summary, entities, keywords, content_hash, last_indexed)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (doc.path, doc.filename, doc.folder, parent_folder, project_folder, relative_path,
             doc.extension, doc.size_bytes, doc.modified_ts, doc.summary, doc.entities_json,
             doc.keywords, doc.content_hash, time.time())
        )
        doc_id = cursor.lastrowid
        
    conn.commit()
    return doc_id

def get_document_by_path(path: str) -> Optional[IndexedDocument]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, path, filename, folder, parent_folder, project_folder, relative_path, "
        "extension, size_bytes, modified_ts, summary, entities, keywords, content_hash, last_indexed "
        "FROM docs WHERE path = ?",
        (path,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_doc(row)

def get_document_by_id(doc_id: int) -> Optional[IndexedDocument]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, path, filename, folder, parent_folder, project_folder, relative_path, "
        "extension, size_bytes, modified_ts, summary, entities, keywords, content_hash, last_indexed "
        "FROM docs WHERE id = ?",
        (doc_id,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_doc(row)

def get_documents_by_ids(doc_ids: List[int]) -> List[IndexedDocument]:
    if not doc_ids:
        return []
    
    conn = _get_conn()
    placeholders = ",".join("?" * len(doc_ids))
    rows = conn.execute(
        f"SELECT id, path, filename, folder, parent_folder, project_folder, relative_path, "
        f"extension, size_bytes, modified_ts, summary, entities, keywords, content_hash, last_indexed "
        f"FROM docs WHERE id IN ({placeholders})",
        doc_ids
    ).fetchall()
    
    return [_row_to_doc(r) for r in rows]

def search_documents_by_keyword(tokens: List[str], max_results: int = 50) -> List[IndexedDocument]:
    """Retrieve documents whose filename, folder, parent/project folder, or keywords match query tokens."""
    if not tokens:
        return []
        
    conn = _get_conn()
    clauses = []
    params = []
    
    for tok in tokens:
        if len(tok) < 2:
            continue
        like_p = f"%{tok}%"
        clauses.append("(filename LIKE ? OR folder LIKE ? OR parent_folder LIKE ? OR project_folder LIKE ? OR keywords LIKE ?)")
        params.extend([like_p, like_p, like_p, like_p, like_p])
        
    if not clauses:
        return []
        
    where_sql = " OR ".join(clauses)
    query_sql = (
        f"SELECT id, path, filename, folder, parent_folder, project_folder, relative_path, "
        f"extension, size_bytes, modified_ts, summary, entities, keywords, content_hash, last_indexed "
        f"FROM docs WHERE {where_sql} LIMIT ?"
    )
    params.append(max_results)
    
    try:
        rows = conn.execute(query_sql, params).fetchall()
        return [_row_to_doc(r) for r in rows]
    except Exception as e:
        logger.debug(f"Keyword search failed: {e}")
        return []

def get_all_documents() -> List[IndexedDocument]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, path, filename, folder, parent_folder, project_folder, relative_path, "
        "extension, size_bytes, modified_ts, summary, entities, keywords, content_hash, last_indexed FROM docs"
    ).fetchall()
    return [_row_to_doc(r) for r in rows]

def get_documents_in_folder_recursive(folder_paths_or_names: List[str]) -> List[IndexedDocument]:
    """Retrieve all indexed documents located within target folder paths or matching project/parent folder names."""
    if not folder_paths_or_names:
        return []
        
    conn = _get_conn()
    clauses = []
    params = []
    
    for item in folder_paths_or_names:
        norm = item.replace("/", "\\").rstrip("\\").lower()
        like_prefix = f"{norm}\\%"
        like_exact = norm
        like_name = f"%{norm}%"
        
        clauses.append("(LOWER(path) LIKE ? OR LOWER(path) = ? OR LOWER(project_folder) LIKE ? OR LOWER(parent_folder) LIKE ? OR LOWER(folder) LIKE ?)")
        params.extend([like_prefix, like_exact, like_name, like_name, like_name])
        
    where_sql = " OR ".join(clauses)
    query_sql = (
        f"SELECT id, path, filename, folder, parent_folder, project_folder, relative_path, "
        f"extension, size_bytes, modified_ts, summary, entities, keywords, content_hash, last_indexed "
        f"FROM docs WHERE {where_sql}"
    )
    try:
        rows = conn.execute(query_sql, params).fetchall()
        return [_row_to_doc(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to fetch documents in folder recursive: {e}")
        return []

def find_matching_folder_paths(folder_candidates: List[str]) -> Tuple[List[str], str]:
    """Find indexed matching folder paths and detected folder candidate label using SQL."""
    if not folder_candidates:
        return [], ""
        
    GENERIC_FOLDERS = {"documents", "desktop", "downloads", "pictures", "projects", "workspaces", "onedrive", "users", "hp", "home", "file", "files", "folder", "folders", "explorer", "c:", "d:", "e:"}
    conn = _get_conn()
    matched_paths = set()
    detected_label = ""
    
    for cand in folder_candidates:
        if not cand or len(cand) < 2:
            continue
            
        norm_cand = cand.lower().replace("_", "").replace("-", "").replace(" ", "")
        if norm_cand in GENERIC_FOLDERS:
            continue
            
        like_p = f"%{cand.lower()}%"
        like_norm = f"%{norm_cand}%"
        
        try:
            rows = conn.execute(
                """
                SELECT DISTINCT project_folder, parent_folder, folder, path FROM docs
                WHERE LOWER(project_folder) LIKE ? OR LOWER(parent_folder) LIKE ? OR LOWER(folder) LIKE ?
                   OR LOWER(REPLACE(REPLACE(REPLACE(project_folder, '_', ''), '-', ''), ' ', '')) LIKE ?
                   OR LOWER(REPLACE(REPLACE(REPLACE(parent_folder, '_', ''), '-', ''), ' ', '')) LIKE ?
                   OR LOWER(REPLACE(REPLACE(REPLACE(folder, '_', ''), '-', ''), ' ', '')) LIKE ?
                   OR LOWER(path) LIKE ?
                """,
                (like_p, like_p, like_p, like_norm, like_norm, like_norm, like_norm)
            ).fetchall()
            
            if rows:
                for row in rows:
                    proj, parent, fld, pth = row
                    for item in [proj, parent, fld]:
                        if item and item.lower() not in GENERIC_FOLDERS:
                            matched_paths.add(item)
                    parts = pth.split(os.sep)
                    for i, p in enumerate(parts):
                        norm_p = p.lower().replace("_", "").replace("-", "").replace(" ", "")
                        if (norm_p == norm_cand or norm_cand in norm_p) and norm_p not in GENERIC_FOLDERS:
                            matched_paths.add(os.sep.join(parts[:i+1]))
                            break
                            
                if not detected_label:
                    detected_label = cand
        except Exception as e:
            logger.debug(f"Folder matching SQL error: {e}")
            
    return list(matched_paths), detected_label

def delete_document_by_path(path: str) -> Optional[int]:
    """Delete a document and return its ID (so we can remove it from FAISS)."""
    conn = _get_conn()
    row = conn.execute("SELECT id FROM docs WHERE path = ?", (path,)).fetchone()
    if not row:
        return None
        
    doc_id = row[0]
    conn.execute("DELETE FROM docs WHERE id = ?", (doc_id,))
    conn.commit()
    return doc_id

def get_last_scan_time() -> float:
    conn = _get_conn()
    row = conn.execute("SELECT value FROM meta WHERE key = 'last_full_scan'").fetchone()
    if row is None:
        return 0.0
    try:
        return float(row[0])
    except:
        return 0.0

def set_last_scan_time(ts: float) -> None:
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_full_scan', ?)",
        (str(ts),)
    )
    conn.commit()

def get_indexed_count() -> int:
    conn = _get_conn()
    row = conn.execute("SELECT COUNT(*) FROM docs").fetchone()
    return row[0] if row else 0

def purge_stale_documents(valid_disk_paths: Optional[set] = None) -> List[int]:
    """Check all indexed documents against physical disk paths (or os.path.exists).
    Deletes any row whose file no longer exists on disk.
    Returns list of deleted doc IDs so they can be removed from FAISS.
    """
    conn = _get_conn()
    rows = conn.execute("SELECT id, path FROM docs").fetchall()
    deleted_ids = []
    
    for doc_id, path in rows:
        if valid_disk_paths is not None:
            exists = path in valid_disk_paths or os.path.exists(path)
        else:
            exists = os.path.exists(path)
            
        if not exists:
            conn.execute("DELETE FROM docs WHERE id = ?", (doc_id,))
            deleted_ids.append(doc_id)
            
    if deleted_ids:
        conn.commit()
        logger.info(f"[METADATA] Purged {len(deleted_ids)} stale document entries from SQLite.")
        
    return deleted_ids

def _row_to_doc(row: tuple) -> IndexedDocument:
    return IndexedDocument(
        id=row[0], path=row[1], filename=row[2], folder=row[3],
        parent_folder=row[4], project_folder=row[5], relative_path=row[6],
        extension=row[7], size_bytes=row[8], modified_ts=row[9], summary=row[10],
        entities_json=row[11], keywords=row[12], content_hash=row[13], last_indexed=row[14]
    )
