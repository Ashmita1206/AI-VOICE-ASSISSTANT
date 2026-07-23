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
        """Open a file using native Windows default application with detailed logging and multi-trigger execution."""
        abs_path = os.path.abspath(path)
        norm_path = os.path.normpath(abs_path)
        exists = os.path.exists(norm_path)
        ext = os.path.splitext(norm_path)[1]

        print("=" * 60)
        print(f"[DOC LAUNCH AUDIT] Absolute path: {norm_path}")
        print(f"[DOC LAUNCH AUDIT] Exists: {exists}")
        print(f"[DOC LAUNCH AUDIT] Extension: {ext}")
        logger.info("[DOC LAUNCH AUDIT] Path=%s Exists=%s Ext=%s", norm_path, exists, ext)

        if not exists:
            logger.error("[DOC LAUNCH AUDIT] File does not exist: %s", norm_path)
            print(f"[DOC LAUNCH AUDIT] Exception: FileNotFoundError - {norm_path} does not exist")
            print("=" * 60)
            return False

        launched = False

        # Method 1: os.startfile(norm_path)
        if hasattr(os, "startfile"):
            try:
                print(f"[DOC LAUNCH AUDIT] Launching via: os.startfile('{norm_path}')")
                os.startfile(norm_path)
                print("[DOC LAUNCH AUDIT] os.startfile executed successfully.")
                logger.info("[DOC LAUNCH AUDIT] os.startfile executed for: %s", norm_path)
                print("=" * 60)
                return True
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                print(f"[DOC LAUNCH AUDIT] Exception in os.startfile: {e}\n{tb}")
                logger.warning("[DOC LAUNCH AUDIT] os.startfile exception: %s", e)

        # Method 2: ShellExecuteW (fallback if os.startfile failed)
        try:
            import ctypes
            print(f"[DOC LAUNCH AUDIT] Launching via: ShellExecuteW('{norm_path}')")
            ret = ctypes.windll.shell32.ShellExecuteW(None, "open", norm_path, None, None, 1)
            print(f"[DOC LAUNCH AUDIT] ShellExecuteW return code: {ret}")
            if ret > 32:
                print("=" * 60)
                return True
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"[DOC LAUNCH AUDIT] Exception in ShellExecuteW: {e}\n{tb}")
            logger.warning("[DOC LAUNCH AUDIT] ShellExecuteW exception: %s", e)

        # Method 3: subprocess cmd /c start "" "path" (fallback 2)
        try:
            import subprocess
            print(f'[DOC LAUNCH AUDIT] Launching via: subprocess cmd start "" "{norm_path}"')
            subprocess.Popen(f'cmd /c start "" "{norm_path}"', shell=True)
            print("[DOC LAUNCH AUDIT] cmd start process spawned successfully.")
            logger.info("[DOC LAUNCH AUDIT] cmd start spawned for: %s", norm_path)
            print("=" * 60)
            return True
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"[DOC LAUNCH AUDIT] Exception in cmd start: {e}\n{tb}")
            logger.warning("[DOC LAUNCH AUDIT] cmd start exception: %s", e)

        # Method 4: subprocess explorer.exe "path" (fallback 3)
        try:
            import subprocess
            print(f'[DOC LAUNCH AUDIT] Launching via: subprocess explorer.exe "{norm_path}"')
            subprocess.Popen(["explorer.exe", norm_path])
            print("[DOC LAUNCH AUDIT] explorer.exe process spawned successfully.")
            logger.info("[DOC LAUNCH AUDIT] explorer.exe spawned for: %s", norm_path)
            print("=" * 60)
            return True
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"[DOC LAUNCH AUDIT] Exception in explorer.exe: {e}\n{tb}")
            logger.warning("[DOC LAUNCH AUDIT] explorer.exe exception: %s", e)

        print("=" * 60)
        return False
