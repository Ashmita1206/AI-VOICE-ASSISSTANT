"""
Document Retrieval Manager
==========================

Singleton interface for the entire document retrieval engine.
"""

import logging
import os
from typing import List, Optional

from agentic.document_retrieval.indexer import DocumentIndexer
from agentic.document_retrieval.schemas import IndexerStatus, SearchResult
from agentic.document_retrieval.watcher import DocumentWatcher
from agentic.document_retrieval import metadata, search, preview

logger = logging.getLogger(__name__)

class DocumentRetrievalManager:
    """Static singleton interface for document retrieval."""
    
    _indexer: Optional[DocumentIndexer] = None
    _watcher: Optional[DocumentWatcher] = None
    
    @classmethod
    def start_indexer(cls) -> None:
        """Start the background indexer and file watcher."""
        if cls._indexer is None:
            cls._indexer = DocumentIndexer()
            cls._indexer.start()
            
            # Start watcher alongside
            cls._watcher = DocumentWatcher(cls._indexer)
            
            # The watcher needs to wait for the first scan to finish
            import threading
            def start_watcher():
                cls._indexer.wait_until_ready()
                cls._watcher.start()
            
            threading.Thread(target=start_watcher, daemon=True).start()
            
    @classmethod
    def stop_indexer(cls) -> None:
        """Stop background tasks."""
        if cls._watcher:
            cls._watcher.stop()
        if cls._indexer:
            cls._indexer.stop()
            
    @classmethod
    def find_documents(cls, query: str, top_n: int = 5) -> List[SearchResult]:
        """Perform a semantic search for documents."""
        # Ensure it's started
        if cls._indexer is None:
            cls.start_indexer()
            
        return search.search_documents(query, top_n)
        
    @classmethod
    def get_indexer_status(cls) -> IndexerStatus:
        """Get the current status of the indexing engine."""
        return IndexerStatus(
            is_running=cls._indexer._is_running if cls._indexer else False,
            is_ready=cls._indexer.is_ready if cls._indexer else False,
            indexed_count=metadata.get_indexed_count(),
            last_scan=metadata.get_last_scan_time(),
            is_watching=cls._watcher.is_watching if cls._watcher else False
        )
        
    @classmethod
    def debug_index(cls, folder_path: str = None) -> dict:
        """Phase 11 Debug API: Audit folder path against filesystem vs SQLite vs FAISS."""
        if cls._indexer is None:
            cls._indexer = DocumentIndexer()
        return cls._indexer.debug_index(folder_path)

    @classmethod
    def open_result(cls, path: str) -> bool:
        """Open a file using native Windows default application."""
        norm_path = os.path.normpath(path)
        if not os.path.exists(norm_path):
            logger.error(f"[RETRIEVAL] File does not exist: {norm_path}")
            return False
            
        try:
            if hasattr(os, "startfile"):
                os.startfile(norm_path)
            else:
                import subprocess
                subprocess.Popen(f'start "" "{norm_path}"', shell=True)
            logger.info(f"[RETRIEVAL] Opened document in native default application: {norm_path}")
            return True
        except Exception as e:
            logger.error(f"[RETRIEVAL] Failed to open document {norm_path}: {e}")
            return False
