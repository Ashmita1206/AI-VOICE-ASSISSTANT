"""
Background Document Indexer
============================

Manages the lifecycle of drive scanning and indexing in a daemon thread
so the Flask server is never blocked.

Workflow
--------
1. On ``start()``, a daemon thread is launched.
2. The thread performs a full scan (or incremental if a recent index exists).
3. After the initial scan, it sleeps and re-scans periodically (every 30 min).
4. Each file is checked: if its ``modified_ts`` has changed or it is not yet
   in the DB, it is re-extracted and re-embedded.
5. Files that no longer exist on disk are removed from the index.

Thread safety
-------------
All DB writes go through ``cache.py`` which uses per-thread SQLite
connections with WAL mode — safe for concurrent access.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from agentic.document_search import cache
from agentic.document_search.schemas import IndexedFile
from agentic.document_search.scanner import scan_drives
from agentic.document_search.embeddings import (
    extract_text,
    extract_keywords,
    extract_summary,
    generate_embedding,
)

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────
RESCAN_INTERVAL_SECONDS: int = 30 * 60   # 30 minutes
BATCH_SIZE: int = 50                      # files per embedding batch
MAX_WORKERS: int = 4                      # extractor thread-pool size


class DocumentIndexer:
    """Manages background scanning and indexing of local documents.

    Usage::

        indexer = DocumentIndexer()
        indexer.start()   # launches daemon thread; returns immediately

    The indexer is designed to be used as a singleton via
    :mod:`agentic.document_search.manager`.
    """

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_running = False
        self._index_ready = threading.Event()  # set once first scan is done

    # ── Public API ─────────────────────────────────────────────────────────

    def start(self) -> None:
        """Launch the background indexer daemon thread (idempotent)."""
        if self._is_running:
            return
        cache.init_db()
        self._is_running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            name="DocumentIndexer",
            daemon=True,
        )
        self._thread.start()
        logger.info("[INDEXER] Background indexer started.")

    def stop(self) -> None:
        """Signal the indexer to stop after its current scan finishes."""
        self._stop_event.set()
        self._is_running = False
        logger.info("[INDEXER] Stop requested.")

    def wait_until_ready(self, timeout: float = 60.0) -> bool:
        """Block until the first scan is complete (or timeout expires).

        Returns True if the index is ready, False if timed out.
        """
        return self._index_ready.wait(timeout=timeout)

    @property
    def is_ready(self) -> bool:
        """True once the first scan has completed."""
        return self._index_ready.is_set()

    def trigger_rescan(self) -> None:
        """Force an immediate re-scan (non-blocking)."""
        if self._thread and self._thread.is_alive():
            # Wake the sleeping loop
            self._stop_event.set()
            self._stop_event.clear()

    # ── Private loop ───────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """Main loop: full scan → sleep → incremental scan → repeat."""
        while not self._stop_event.is_set():
            try:
                self._perform_scan()
            except Exception as exc:
                logger.error("[INDEXER] Scan error: %s", exc, exc_info=True)

            if not self._index_ready.is_set():
                self._index_ready.set()

            logger.info(
                "[INDEXER] Scan complete. Next scan in %d seconds.",
                RESCAN_INTERVAL_SECONDS,
            )
            self._stop_event.wait(timeout=RESCAN_INTERVAL_SECONDS)

    def _perform_scan(self) -> None:
        """Execute one full/incremental scan pass."""
        start_ts = time.time()
        last_scan = cache.get_last_scan_time()
        is_full_scan = last_scan == 0.0

        if is_full_scan:
            logger.info("[INDEXER] Starting FULL scan of all drives…")
        else:
            logger.info(
                "[INDEXER] Starting INCREMENTAL scan (last full scan: %.0f s ago)…",
                time.time() - last_scan,
            )

        # Build a set of paths currently on disk
        paths_on_disk: set[str] = set()
        files_to_index: list[tuple[str, os.stat_result]] = []

        for file_path, stat in scan_drives():
            if self._stop_event.is_set():
                logger.info("[INDEXER] Scan interrupted by stop signal.")
                return

            paths_on_disk.add(file_path)
            existing = cache.get_file_by_path(file_path)

            if existing is None:
                # New file — index it
                files_to_index.append((file_path, stat))
            elif existing.modified_ts != stat.st_mtime:
                # File changed — re-index it
                files_to_index.append((file_path, stat))
            # else: unchanged — skip

        logger.info(
            "[INDEXER] Found %d files to (re-)index out of %d on disk.",
            len(files_to_index),
            len(paths_on_disk),
        )

        # Index files using a thread pool
        if files_to_index:
            self._index_batch(files_to_index)

        # Remove stale entries (files deleted from disk)
        if is_full_scan:
            self._purge_deleted(paths_on_disk)

        elapsed = time.time() - start_ts
        cache.set_last_scan_time(time.time())
        total_indexed = cache.get_indexed_count()
        logger.info(
            "[INDEXER] Scan finished in %.1f s. Total indexed: %d files.",
            elapsed, total_indexed,
        )

    def _index_batch(self, files: list[tuple[str, os.stat_result]]) -> None:
        """Process a batch of files through extractor + embedder with a thread pool."""
        with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="Indexer") as pool:
            futures = {
                pool.submit(self._index_single_file, fp, st): fp
                for fp, st in files
            }
            done_count = 0
            for future in as_completed(futures):
                if self._stop_event.is_set():
                    pool.shutdown(wait=False)
                    return
                path = futures[future]
                try:
                    future.result()
                    done_count += 1
                    if done_count % 100 == 0:
                        logger.info("[INDEXER] Indexed %d / %d files…", done_count, len(files))
                except Exception as exc:
                    logger.debug("[INDEXER] Failed to index %s: %s", path, exc)

    def _index_single_file(self, file_path: str, stat: os.stat_result) -> None:
        """Extract text, generate embedding, and upsert into the DB."""
        p = Path(file_path)
        ext = p.suffix.lower().lstrip(".")
        folder_path = str(p.parent)
        folder_name = p.parent.name

        text = extract_text(file_path)
        keywords = extract_keywords(text) if text else ""
        summary = extract_summary(text) if text else ""

        # Build embedding input: filename + keywords + first 300 chars of text
        embed_input = f"{p.stem} {keywords} {text[:300]}".strip()
        embedding_blob = generate_embedding(embed_input)

        record = IndexedFile(
            path=file_path,
            filename=p.name,
            extension=ext,
            size_bytes=stat.st_size,
            modified_ts=stat.st_mtime,
            folder=folder_name,
            folder_path=folder_path,
            sample_text=text[:2000],
            keywords=keywords,
            summary=summary,
            embedding_blob=embedding_blob,
        )
        cache.upsert_file(record)

    def _purge_deleted(self, paths_on_disk: set[str]) -> None:
        """Remove index entries for files that no longer exist on disk."""
        all_indexed = cache.get_all_files(with_embeddings=False)
        removed = 0
        for f in all_indexed:
            if f.path not in paths_on_disk:
                cache.delete_file(f.path)
                removed += 1
        if removed:
            logger.info("[INDEXER] Purged %d stale entries from index.", removed)
