"""
Document Retrieval Watcher
==========================

Real-time filesystem observation using watchdog.
"""

import logging
import os
import threading
import time
from typing import Optional

from agentic.document_retrieval import cache, config, metadata, scanner
from agentic.document_retrieval.indexer import DocumentIndexer

logger = logging.getLogger(__name__)

class DocumentWatcher:
    """Watches the filesystem for changes and triggers incremental indexing."""
    
    def __init__(self, indexer: DocumentIndexer):
        self.indexer = indexer
        self.observers = []
        self._is_watching = False
        
    def start(self):
        if self._is_watching:
            return
            
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            logger.error("[WATCHER] watchdog not installed. Real-time updates disabled.")
            return
            
        class IndexEventHandler(FileSystemEventHandler):
            def __init__(self, indexer):
                self.indexer = indexer
                
            def on_created(self, event):
                if not event.is_directory:
                    self._handle_change(event.src_path)
                    
            def on_modified(self, event):
                if not event.is_directory:
                    self._handle_change(event.src_path)
                    
            def on_deleted(self, event):
                if not event.is_directory:
                    self._handle_delete(event.src_path)
                    
            def on_moved(self, event):
                if not event.is_directory:
                    self._handle_delete(event.src_path)
                    self._handle_change(event.dest_path)
                    
            def _handle_change(self, path: str):
                # Filter by extension and skip dirs
                ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
                if ext not in config.SUPPORTED_EXTENSIONS:
                    return
                    
                dirpath, dirname = os.path.split(os.path.dirname(path))
                if scanner._should_skip_dir(dirpath, dirname):
                    return
                    
                logger.debug(f"[WATCHER] File changed: {path}")
                # We wait a bit to ensure the file is completely written
                time.sleep(1.0)
                # We do this asynchronously to avoid blocking the watcher
                threading.Thread(target=self.indexer.index_single_file_sync, args=(path,), daemon=True).start()
                
            def _handle_delete(self, path: str):
                ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
                if ext not in config.SUPPORTED_EXTENSIONS:
                    return
                logger.debug(f"[WATCHER] File deleted: {path}")
                doc_id = metadata.delete_document_by_path(path)
                if doc_id:
                    cache.remove_embeddings([doc_id])

        handler = IndexEventHandler(self.indexer)
        
        roots = scanner._get_drives()
        for root in roots:
            if not os.path.exists(root):
                continue
            
            try:
                observer = Observer()
                observer.schedule(handler, path=root, recursive=True)
                observer.start()
                self.observers.append(observer)
                logger.info(f"[WATCHER] Started observing: {root}")
            except Exception as e:
                logger.error(f"[WATCHER] Failed to start observer for {root}: {e}")
                
        self._is_watching = True
        
    def stop(self):
        for observer in self.observers:
            observer.stop()
        for observer in self.observers:
            observer.join()
        self.observers = []
        self._is_watching = False
        logger.info("[WATCHER] Stopped all observers.")
        
    @property
    def is_watching(self) -> bool:
        return self._is_watching
