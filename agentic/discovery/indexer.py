"""
Background Indexer
==================

Manages background resource scanning and persistent indexing.
"""

import os
import json
import time
import threading
import logging
from typing import List

from agentic.discovery.schemas import Resource
from agentic.discovery.apps import scan_installed_apps
from agentic.discovery.browser import scan_bookmarks, scan_history
from agentic.discovery.filesystem import scan_home_directories, search_recent_files, search_recent_folders
from agentic.discovery.processes import scan_running_processes

logger = logging.getLogger(__name__)

# Base directory for cache
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
INDEX_PATH = os.path.join(CACHE_DIR, "system_index.json")

class SystemIndexer:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SystemIndexer, cls).__new__(cls)
                cls._instance._init()
            return cls._instance
            
    def _init(self):
        self.resources: List[Resource] = []
        self._thread = None
        self._stop_event = threading.Event()
        self.last_scanned = 0.0
        
    def start(self, interval_seconds: int = 300):
        """Start background indexing thread."""
        if self._thread and self._thread.is_alive():
            return
            
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(interval_seconds,),
            name="SystemIndexerThread",
            daemon=True
        )
        self._thread.start()
        logger.info("System background indexer started.")
        
    def stop(self):
        """Stop background indexing thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("System background indexer stopped.")
        
    def _run_loop(self, interval: int):
        # Do initial scan immediately
        self.scan_and_save()
        while not self._stop_event.wait(interval):
            self.scan_and_save()
            
    def scan_and_save(self):
        """Run scanners, cache resources, and write to disk."""
        logger.info("Starting system resource discovery scan...")
        start_time = time.perf_counter()
        
        try:
            # 1. Scan applications
            apps = scan_installed_apps()
            
            # 2. Scan bookmarks
            bookmarks = scan_bookmarks()
            
            # 3. Scan history
            history = scan_history()
            
            # 4. Scan filesystem
            home_dirs = scan_home_directories()
            recent_files = search_recent_files()
            recent_folders = search_recent_folders()
            
            # 5. Scan processes
            processes = scan_running_processes()
            
            # Map running processes for is_running checks
            running_exes = {p.executable.lower().strip() for p in processes if p.executable}
            running_names = {p.name.lower().strip() for p in processes if p.name}
            
            for app in apps:
                app_exe = (app.executable or "").lower().strip()
                app_basename = os.path.basename(app_exe)
                app_name_lower = app.name.lower().strip()
                
                if (app_exe and app_exe in running_exes) or \
                   (app_basename and app_basename in running_names) or \
                   (app_name_lower and app_name_lower in running_names) or \
                   (app_name_lower + ".exe" in running_names):
                    app.is_running = True
            
            # Combine all resources
            all_res = apps + bookmarks + history + home_dirs + recent_files + recent_folders + processes
            
            # De-duplicate by lower-cased name and type, keeping highest confidence
            deduped = {}
            for res in all_res:
                key = (res.name.lower().strip(), res.type)
                if key not in deduped or res.confidence > deduped[key].confidence:
                    # Carry forward is_running if we are replacing/deduplicating
                    if key in deduped and deduped[key].is_running:
                        res.is_running = True
                    deduped[key] = res
                    
            self.resources = list(deduped.values())
            self.last_scanned = time.time()
            
            # Ensure cache dir exists
            os.makedirs(CACHE_DIR, exist_ok=True)
            
            # Save to disk
            with open(INDEX_PATH, "w", encoding="utf-8") as f:
                json.dump([r.to_dict() for r in self.resources], f, indent=2, ensure_ascii=False)
                
            elapsed = time.perf_counter() - start_time
            logger.info(f"System resource scan completed in {elapsed:.2f}s. Indexed {len(self.resources)} resources.")
        except Exception as e:
            logger.exception(f"Error during system resource scan: {e}")
            
    def load_index(self) -> List[Resource]:
        """Load index from disk or scan if not exists/empty."""
        if not self.resources:
            if os.path.exists(INDEX_PATH):
                try:
                    with open(INDEX_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.resources = [Resource.from_dict(d) for d in data]
                except Exception as e:
                    logger.warning(f"Failed to load system index from disk: {e}")
                    self.scan_and_save()
            else:
                self.scan_and_save()
        return self.resources

def get_indexer() -> SystemIndexer:
    return SystemIndexer()
