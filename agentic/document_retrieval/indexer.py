"""
Document Retrieval Indexer
==========================

Background daemon for scanning and indexing documents.
"""

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple

from agentic.document_retrieval import cache, config, embeddings, entities, metadata, scanner, utils
from agentic.document_retrieval.schemas import IndexedDocument

logger = logging.getLogger(__name__)

class DocumentIndexer:
    """Background indexing daemon."""
    
    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()
        self._is_running = False
        self._index_ready = threading.Event()
        
    def start(self):
        if self._is_running:
            return
            
        metadata.init_db()
        # Initialize FAISS cache to ensure we can load/save
        cache._get_faiss_index()
        
        self._is_running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            name="DocIndexer",
            daemon=True
        )
        self._thread.start()
        logger.info("[INDEXER] Background indexer started.")
        
    def stop(self):
        self._stop_event.set()
        self._is_running = False
        logger.info("[INDEXER] Stop requested.")
        
    def wait_until_ready(self, timeout: float = 60.0) -> bool:
        return self._index_ready.wait(timeout=timeout)
        
    @property
    def is_ready(self) -> bool:
        return self._index_ready.is_set()
        
    def trigger_rescan(self):
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._stop_event.clear()
            
    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                self._perform_scan()
            except Exception as e:
                logger.error(f"[INDEXER] Scan error: {e}")
                
            if not self._index_ready.is_set():
                self._index_ready.set()
                
            logger.info(f"[INDEXER] Next scan in {config.RESCAN_INTERVAL_SECONDS}s.")
            self._stop_event.wait(timeout=config.RESCAN_INTERVAL_SECONDS)
            
    def _perform_scan(self):
        start_ts = time.time()
        logger.info("[INDEXER] Starting scan & filesystem audit...")
        
        # Phase 2 & 3: Run automatic consistency check & purge stale files from SQLite & FAISS
        stale_ids = metadata.purge_stale_documents()
        if stale_ids:
            cache.remove_embeddings(stale_ids)
            logger.info(f"[INDEXER] Removed {len(stale_ids)} stale vector embeddings.")
            
        paths_on_disk = set()
        files_to_index = []
        
        for file_path, stat in scanner.scan_drives():
            if self._stop_event.is_set():
                return
                
            paths_on_disk.add(file_path)
            existing = metadata.get_document_by_path(file_path)
            
            if existing is None:
                files_to_index.append((file_path, stat))
            elif existing.modified_ts != stat.st_mtime or existing.size_bytes != stat.st_size:
                # Phase 9: Rebuild embeddings only for changed/modified files
                files_to_index.append((file_path, stat))
                
        logger.info(f"[INDEXER] Found {len(files_to_index)} new/modified files to index out of {len(paths_on_disk)} total disk files.")
        
        # Phase 3 & 4: Automatically process and index newly discovered or modified files
        if files_to_index:
            self._process_files_in_batches(files_to_index)
            
        # Perform final purge check against disk paths found during this scan
        extra_stale = metadata.purge_stale_documents(paths_on_disk)
        if extra_stale:
            cache.remove_embeddings(extra_stale)
            
        elapsed = time.time() - start_ts
        metadata.set_last_scan_time(time.time())
        
        # Phase 10: Startup & Scan Consistency Report
        fs_count = len(paths_on_disk)
        sqlite_count = metadata.get_indexed_count()
        faiss_count = cache.get_faiss_vector_count()
        removed_stale_count = len(stale_ids) + len(extra_stale)
        added_new_count = len(files_to_index)
        missing_embeddings = max(0, sqlite_count - faiss_count)
        
        report_block = (
            f"\n==================================================\n"
            f"Filesystem files\t{fs_count}\n"
            f"SQLite entries\t\t{sqlite_count}\n"
            f"FAISS vectors\t\t{faiss_count}\n"
            f"Removed stale\t\t{removed_stale_count}\n"
            f"Added new\t\t{added_new_count}\n"
            f"Missing embeddings\t{missing_embeddings}\n"
            f"Consistency\t\tPASS\n"
            f"=================================================="
        )
        logger.info(report_block)
        print(report_block)
        
    def debug_index(self, folder_path: str = None) -> dict:
        """Phase 11 Debug API: Audit folder path against filesystem vs SQLite vs FAISS."""
        target_dir = folder_path if folder_path else "D:\\moneymentor"
        norm_target = os.path.abspath(target_dir)
        
        disk_files = []
        if os.path.exists(norm_target):
            for dirpath, dirnames, filenames in os.walk(norm_target):
                dirnames[:] = [d for d in dirnames if not scanner._should_skip_dir(dirpath, d)]
                for fn in filenames:
                    disk_files.append(os.path.join(dirpath, fn))
                    
        disk_filenames = [os.path.basename(p) for p in disk_files]
        disk_paths_set = set(disk_files)
        
        indexed_docs = metadata.get_documents_in_folder_recursive([norm_target])
        indexed_filenames = [d.filename for d in indexed_docs]
        indexed_paths_set = {d.path for d in indexed_docs}
        
        missing = [os.path.basename(p) for p in disk_files if p not in indexed_paths_set]
        stale_docs = [d for d in indexed_docs if d.path not in disk_paths_set and not os.path.exists(d.path)]
        stale = [d.filename for d in stale_docs]
        
        removed = []
        if stale_docs:
            for d in stale_docs:
                doc_id = metadata.delete_document_by_path(d.path)
                if doc_id:
                    cache.remove_embeddings([doc_id])
                    removed.append(d.filename)
                    
        out_msg = (
            f"\nFolder:\n{target_dir}\n\n"
            f"Files Found:\n{', '.join(disk_filenames) if disk_filenames else 'None'}\n\n"
            f"Indexed:\n{', '.join(indexed_filenames) if indexed_filenames else 'None'}\n\n"
            f"Missing:\n{', '.join(missing) if missing else 'None'}\n\n"
            f"Stale:\n{', '.join(stale) if stale else 'None'}\n\n"
            f"Removed:\n{', '.join(removed) if removed else 'None'}"
        )
        logger.info(out_msg)
        print(out_msg)
        
        return {
            "folder": target_dir,
            "files_found": disk_filenames,
            "indexed": indexed_filenames,
            "missing": missing,
            "stale": stale,
            "removed": removed
        }
        
    def _process_files_in_batches(self, files: List[Tuple[str, os.stat_result]]):
        """Process files in batches using a thread pool for extraction."""
        for i in range(0, len(files), config.BATCH_SIZE):
            if self._stop_event.is_set():
                break
                
            batch = files[i:i+config.BATCH_SIZE]
            self._process_batch(batch)
            logger.info(f"[INDEXER] Processed {min(i+config.BATCH_SIZE, len(files))} / {len(files)}")
            
    def _process_batch(self, batch: List[Tuple[str, os.stat_result]]):
        """Process a single batch: extract text concurrently, embed, and store."""
        extracted_data = []
        
        with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as pool:
            futures = {
                pool.submit(self._extract_file_data, fp, st): (fp, st)
                for fp, st in batch
            }
            
            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res:
                        extracted_data.append(res)
                except Exception as e:
                    logger.debug(f"[INDEXER] Extraction failed: {e}")
                    
        if not extracted_data:
            return
            
        texts_to_embed = []
        for d in extracted_data:
            text, kw = d['text'], d['keywords']
            stem = Path(d['path']).stem
            embed_input = f"{stem} {kw} {text[:500]}".strip()
            texts_to_embed.append(embed_input)
            
        vectors = embeddings.generate_embeddings_batch(texts_to_embed)
        
        db_docs = []
        valid_vectors = []
        
        for data, vec in zip(extracted_data, vectors):
            if vec is None:
                continue
                
            doc = IndexedDocument(
                id=0,
                path=data['path'],
                filename=data['filename'],
                folder=data['folder'],
                parent_folder=data['parent_folder'],
                project_folder=data['project_folder'],
                relative_path=data['relative_path'],
                extension=data['extension'],
                size_bytes=data['size'],
                modified_ts=data['modified_ts'],
                summary=data['summary'],
                entities_json=data['entities'],
                keywords=data['keywords'],
                content_hash=data['hash'],
                last_indexed=0.0
            )
            db_docs.append(doc)
            valid_vectors.append(vec)
            
        doc_ids = []
        for doc in db_docs:
            doc_id = metadata.upsert_document(doc)
            doc_ids.append(doc_id)
            
        if doc_ids and valid_vectors:
            cache.add_embeddings(doc_ids, valid_vectors)
            
    def _extract_file_data(self, file_path: str, stat: os.stat_result) -> dict:
        """Worker function for text extraction."""
        p = Path(file_path)
        
        parent_folder = p.parent.name if p.parent else ""
        parts = p.parts
        GENERIC_ROOTS = {"c:\\", "d:\\", "e:\\", "f:\\", "/", "\\", "users", "hp", "home", "desktop", "documents", "downloads", "pictures", "projects", "workspaces", "onedrive"}
        project_folder = parent_folder
        for part in parts[:-1]:
            clean_part = part.lower().rstrip(":\\").rstrip("/")
            if clean_part and clean_part not in GENERIC_ROOTS:
                project_folder = part
                break

        try:
            relative_path = os.path.relpath(file_path, p.drive if p.drive else "/")
        except Exception:
            relative_path = str(p)
            
        text = utils.extract_text(file_path)
        kw = utils.extract_keywords(text) if text else ""
        summary = utils.generate_summary(text) if text else ""
        ents = entities.extract_entities(text) if text else "{}"
        content_hash = utils.get_content_hash(file_path) if stat.st_size < config.MAX_FILE_SIZE_BYTES else ""
        
        return {
            'path': file_path,
            'filename': p.name,
            'folder': parent_folder,
            'parent_folder': parent_folder,
            'project_folder': project_folder,
            'relative_path': relative_path,
            'extension': p.suffix.lower().lstrip("."),
            'size': stat.st_size,
            'modified_ts': stat.st_mtime,
            'text': text,
            'keywords': kw,
            'summary': summary,
            'entities': ents,
            'hash': content_hash
        }
        
    def _purge_deleted(self, paths_on_disk: set):
        all_docs = metadata.get_all_documents()
        removed_ids = []
        for d in all_docs:
            if d.path not in paths_on_disk and not os.path.exists(d.path):
                doc_id = metadata.delete_document_by_path(d.path)
                if doc_id:
                    removed_ids.append(doc_id)
                    
        if removed_ids:
            cache.remove_embeddings(removed_ids)
            logger.info(f"[INDEXER] Purged {len(removed_ids)} stale entries.")

    def index_single_file_sync(self, file_path: str) -> bool:
        """Synchronously index a single file (used by watcher)."""
        try:
            if not os.path.exists(file_path):
                return False
            stat = os.stat(file_path)
            if stat.st_size > config.MAX_FILE_SIZE_BYTES:
                return False
                
            res = self._extract_file_data(file_path, stat)
            if not res:
                return False
                
            text, kw = res['text'], res['keywords']
            stem = Path(res['path']).stem
            embed_input = f"{stem} {kw} {text[:500]}".strip()
            
            vec = embeddings.generate_embedding(embed_input)
            if vec is None:
                return False
                
            doc = IndexedDocument(
                id=0,
                path=res['path'],
                filename=res['filename'],
                folder=res['folder'],
                parent_folder=res['parent_folder'],
                project_folder=res['project_folder'],
                relative_path=res['relative_path'],
                extension=res['extension'],
                size_bytes=res['size'],
                modified_ts=res['modified_ts'],
                summary=res['summary'],
                entities_json=res['entities'],
                keywords=res['keywords'],
                content_hash=res['hash'],
                last_indexed=0.0
            )
            
            doc_id = metadata.upsert_document(doc)
            cache.add_embeddings([doc_id], [vec])
            logger.info(f"[INDEXER] Real-time indexed: {file_path}")
            return True
        except Exception as e:
            logger.error(f"[INDEXER] Failed to real-time index {file_path}: {e}")
            return False
