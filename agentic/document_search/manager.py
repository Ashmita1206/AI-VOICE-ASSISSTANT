"""
Document Search Manager
========================

Module-level singleton that wires together the indexer and searcher.
This is the single import point for the tool handler.

Usage
-----
    from agentic.document_search.manager import DocumentSearchManager

    # Start the background indexer (call once at app startup or lazily)
    DocumentSearchManager.start_indexer()

    # Search
    results = DocumentSearchManager.find_documents("CDOT proposal")

    # Open a specific result by absolute path (delegates to existing open_file)
    DocumentSearchManager.open_result("/absolute/path/to/file.docx")
"""

from __future__ import annotations

import logging
from typing import List, Optional

from agentic.document_search.indexer import DocumentIndexer
from agentic.document_search.search import ContextDocumentSearch
from agentic.document_search.schemas import SearchResult

logger = logging.getLogger(__name__)

# ── Singletons ─────────────────────────────────────────────────────────────
_indexer: Optional[DocumentIndexer] = None
_searcher: Optional[ContextDocumentSearch] = None


def _get_indexer() -> DocumentIndexer:
    global _indexer
    if _indexer is None:
        _indexer = DocumentIndexer()
    return _indexer


def _get_searcher() -> ContextDocumentSearch:
    global _searcher
    if _searcher is None:
        _searcher = ContextDocumentSearch()
    return _searcher


class DocumentSearchManager:
    """Static interface for the document search feature."""

    @staticmethod
    def start_indexer() -> None:
        """Start the background indexer daemon (idempotent).

        Safe to call multiple times — only starts once.
        """
        indexer = _get_indexer()
        if not indexer.is_ready and not indexer._is_running:
            logger.info("[MANAGER] Starting document indexer…")
            indexer.start()

    @staticmethod
    def find_documents(query: str, top_n: int = 5) -> List[SearchResult]:
        """Locate files matching the user's context description.

        Automatically starts the indexer on first call if it has not been
        started yet.

        Parameters
        ----------
        query:
            Free-form description from the user.
        top_n:
            Maximum results to return (default 5).

        Returns
        -------
        list[SearchResult]
        """
        # Lazy-start indexer
        indexer = _get_indexer()
        if not indexer._is_running:
            logger.info("[MANAGER] Lazy-starting indexer on first search request.")
            indexer.start()

        searcher = _get_searcher()
        return searcher.search(query, top_n=top_n)

    @staticmethod
    def open_result(path: str) -> dict:
        """Open a file at ``path`` using the existing open_file tool handler.

        Returns a dict with ``success`` and ``message`` keys.
        """
        try:
            from automation.filesystem import open_file as _open_file
            from agentic.schemas import ActionStep
            result = _open_file({"path": path})
            return {"success": result.success, "message": result.message}
        except Exception as exc:
            logger.error("[MANAGER] Failed to open file %s: %s", path, exc)
            return {"success": False, "message": str(exc)}

    @staticmethod
    def get_indexer_status() -> dict:
        """Return a status dict describing the current indexer state."""
        from agentic.document_search import cache
        indexer = _get_indexer()
        return {
            "is_running": indexer._is_running,
            "is_ready": indexer.is_ready,
            "indexed_count": cache.get_indexed_count(),
            "last_scan": cache.get_last_scan_time(),
        }
