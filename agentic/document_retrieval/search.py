import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Set, Tuple

from agentic.document_retrieval import cache, metadata
from agentic.document_retrieval.embeddings import generate_embedding
from agentic.document_retrieval.ranking import rank_documents, _folder_score, _filename_score, _bm25_scores, _recency_score, _extension_score, W_FOLDER, W_FILENAME, W_BM25, W_SEMANTIC, W_RECENCY
from agentic.document_retrieval.retriever import parse_query, normalize_query, rewrite_query, normalize_folder_name
from agentic.document_retrieval.schemas import SearchResult, IndexedDocument
from agentic.document_retrieval import config

logger = logging.getLogger(__name__)


def _scan_filesystem_for_folder(folder_candidates: list) -> list:
    """Phase 7 Fallback: Scan drives for directories matching folder candidates.
    Returns list of matching directory absolute paths found on the filesystem.
    """
    if not folder_candidates:
        return []

    # Build normalized targets
    targets = set()
    for fc in folder_candidates:
        norm = normalize_folder_name(fc)
        if norm and len(norm) >= 3:
            targets.add(norm)

    if not targets:
        return []

    matched_dirs = []

    # Scan drive roots for matching top-level directories
    if sys.platform.startswith("win"):
        drives = [f"{letter}:\\" for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{letter}:\\")]
    else:
        drives = ["/"]

    # Also check user home directories
    user_home = os.path.expanduser("~")
    search_roots = list(drives)
    for sub in ["Desktop", "Documents", "Downloads", "Projects", "OneDrive"]:
        p = os.path.join(user_home, sub)
        if os.path.exists(p):
            search_roots.append(p)

    for root in search_roots:
        try:
            for entry in os.scandir(root):
                if entry.is_dir(follow_symlinks=False):
                    dir_norm = normalize_folder_name(entry.name)
                    if dir_norm in targets:
                        matched_dirs.append(entry.path)
        except (PermissionError, OSError):
            continue

    return matched_dirs


def _build_docs_from_folder(folder_path: str) -> List[IndexedDocument]:
    """Scan a physical folder recursively and build IndexedDocument objects for all supported files."""
    from agentic.document_retrieval import scanner

    docs = []
    now = time.time()
    folder_name = os.path.basename(folder_path)

    for dirpath, dirnames, filenames in os.walk(folder_path, topdown=True):
        dirnames[:] = [d for d in dirnames if not scanner._should_skip_dir(dirpath, d)]

        for filename in filenames:
            full_path = os.path.join(dirpath, filename)

            try:
                stat = os.stat(full_path)
            except OSError:
                continue

            if stat.st_size > config.MAX_FILE_SIZE_BYTES or stat.st_size == 0:
                continue

            ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
            if ext in config.NEVER_INDEX_EXTENSIONS:
                continue
            if ext not in config.SUPPORTED_EXTENSIONS:
                continue

            try:
                rel = os.path.relpath(full_path, folder_path)
            except Exception:
                rel = filename

            parent_folder = os.path.basename(dirpath)

            doc = IndexedDocument(
                id=0,
                path=full_path,
                filename=filename,
                folder=parent_folder,
                parent_folder=parent_folder,
                project_folder=folder_name,
                relative_path=rel,
                extension=ext,
                size_bytes=stat.st_size,
                modified_ts=stat.st_mtime,
                summary="",
                entities_json="{}",
                keywords=filename.lower().replace(".", " ").replace("_", " ").replace("-", " "),
                content_hash="",
                last_indexed=now
            )

            # Upsert into SQLite so future searches find it immediately
            doc_id = metadata.upsert_document(doc)
            doc = IndexedDocument(
                id=doc_id, path=doc.path, filename=doc.filename,
                folder=doc.folder, parent_folder=doc.parent_folder,
                project_folder=doc.project_folder, relative_path=doc.relative_path,
                extension=doc.extension, size_bytes=doc.size_bytes,
                modified_ts=doc.modified_ts, summary=doc.summary,
                entities_json=doc.entities_json, keywords=doc.keywords,
                content_hash=doc.content_hash, last_indexed=doc.last_indexed
            )
            docs.append(doc)

    return docs


def search_documents(query: str, top_n: int = 5) -> List[SearchResult]:
    """Perform recursive folder-based search or global fallback retrieval."""
    if not query or not query.strip():
        logger.warning("[SEARCH] Empty query.")
        return []
        
    total_docs = metadata.get_indexed_count()
        
    parsed = parse_query(query)
    normalized = parsed.normalized_query
    expanded = rewrite_query(query)
    folder_candidates = parsed.folder_candidates
    
    logger.info(f"[SEARCH] Raw Query: '{query}' | Normalized: '{normalized}' | Folder Candidates: {folder_candidates}")
    
    # ── STAGE 1 & 2: Folder Recognition & Recursive Folder Search ─────────
    matched_folder_paths: Set[str] = set()
    detected_folder_label = ""
    
    # Check indexed documents for folder name matches via fast SQL lookup
    folder_list, detected_folder_label = metadata.find_matching_folder_paths(folder_candidates)
    matched_folder_paths = set(folder_list)
                    
    candidate_docs: List[IndexedDocument] = []
    
    if matched_folder_paths:
        # Folder match found in SQLite! Build candidate set ONLY from these folders
        folder_list = list(matched_folder_paths)
        candidate_docs = metadata.get_documents_in_folder_recursive(folder_list)
        
        main_matched_folder = folder_list[0]
        detected_name = detected_folder_label if detected_folder_label else os.path.basename(main_matched_folder)
        
        log_block = (
            f"\nDetected Folder:\n{detected_name}\n\n"
            f"Matched Folder:\n{main_matched_folder}\n\n"
            f"Files Found:\n{len(candidate_docs)}"
        )
        logger.info(log_block)
        print(log_block)
        
    elif folder_candidates:
        # ── PHASE 7 FALLBACK: Live filesystem folder scan ─────────────────
        # SQLite has no entries for this folder (not indexed yet).
        # Scan the filesystem directly for matching directories.
        logger.info(f"[SEARCH] No SQLite folder match. Scanning filesystem for: {folder_candidates}")
        
        disk_dirs = _scan_filesystem_for_folder(folder_candidates)
        
        if disk_dirs:
            main_dir = disk_dirs[0]
            detected_name = os.path.basename(main_dir)
            matched_folder_paths = set(disk_dirs)
            
            logger.info(f"[SEARCH] Found folder on disk: {main_dir}. Indexing files on-the-fly...")
            print(f"\nDetected Folder:\n{detected_name}\n\nMatched Folder (live scan):\n{main_dir}")
            
            # Build candidate documents from the physical folder
            for d in disk_dirs:
                candidate_docs.extend(_build_docs_from_folder(d))
            
            log_msg = f"\nFiles Found (live scan):\n{len(candidate_docs)}"
            logger.info(log_msg)
            print(log_msg)
            
            # Log each file discovered
            for doc in candidate_docs:
                print(f"  {doc.filename} | {doc.path}")
        else:
            logger.info("[SEARCH] No matching folders found on filesystem either.")
    
    if not candidate_docs and not matched_folder_paths:
        # STAGE 2 FALLBACK: Global Search only if no folder matched anywhere
        if total_docs == 0:
            logger.info("[SEARCH] Index is empty. Returning nothing.")
            return []
            
        logger.info("[SEARCH] No folder match found. Falling back to global search.")
        candidate_dict = {}
        
        # 1. Vector Search
        query_vector = generate_embedding(expanded)
        if query_vector is not None:
            candidate_limit = min(50, total_docs)
            doc_ids, distances = cache.search(query_vector, top_n=candidate_limit)
            if doc_ids:
                vector_docs = metadata.get_documents_by_ids(doc_ids)
                dist_map = dict(zip(doc_ids, distances))
                for doc in vector_docs:
                    candidate_dict[doc.id] = doc
                    
        # 2. Keyword Search Fallback
        tokens = normalized.split()
        if tokens:
            kw_docs = metadata.search_documents_by_keyword(tokens, max_results=50)
            for doc in kw_docs:
                if doc.id not in candidate_dict:
                    candidate_dict[doc.id] = doc
                    
        candidate_docs = list(candidate_dict.values())

    # ── PHASE 8: Real Filesystem Validation ─────────────────────────────────
    valid_candidates = []
    for doc in candidate_docs:
        if os.path.exists(doc.path):
            valid_candidates.append(doc)
        else:
            doc_id = metadata.delete_document_by_path(doc.path)
            if doc_id:
                cache.remove_embeddings([doc_id])
                logger.info(f"[SEARCH] Discarded non-existent file & purged stale index: {doc.path}")

    if not valid_candidates:
        logger.info("[SEARCH] No physically existing candidates found on disk.")
        return []

    # Calculate semantic distances for valid candidates
    distances = [0.5] * len(valid_candidates)
    if not matched_folder_paths:
        try:
            query_vector = generate_embedding(expanded)
            if query_vector is not None and cache._get_faiss_index() is not None:
                pass
        except Exception:
            pass
        
    # ── STAGE 5: Multi-Signal Ranking ─────────────────────────────────────
    results = rank_documents(
        query=query,
        candidates=valid_candidates,
        semantic_dists=distances,
        top_n=top_n,
        matched_folder_paths=list(matched_folder_paths) if matched_folder_paths else None
    )
    
    # ── PHASE 8: Final Result Validation ──────────────────────────────────
    valid_results = [r for r in results if os.path.exists(r.path)]
    
    # ── STAGE 6: Debug Logging for Top Result ─────────────────────────────
    if valid_results:
        top_res = valid_results[0]
        top_doc = next((d for d in valid_candidates if d.path == top_res.path), valid_candidates[0])
        
        q_tokens = parsed.target_filename_tokens if parsed.target_filename_tokens else normalized.split()
        fo_s = _folder_score(q_tokens, top_doc, matched_folder_paths=list(matched_folder_paths) if matched_folder_paths else None, folder_candidates=folder_candidates)
        fn_s = _filename_score(q_tokens, top_doc.filename)
        bm_s = 0.5
        sem_s = 0.5
        
        stage6_log = (
            f"\nTop Candidate:\n{top_res.filename}\n\n"
            f"Ranking:\n"
            f"FolderScore: {fo_s:.2f}\n"
            f"FilenameScore: {fn_s:.2f}\n"
            f"BM25Score: {bm_s:.2f}\n"
            f"SemanticScore: {sem_s:.2f}\n"
            f"FinalScore: {top_res.score:.4f}"
        )
        logger.info(stage6_log)
        print(stage6_log)
        
    logger.info(f"[SEARCH] Returning {len(valid_results)} validated physical results.")
    return valid_results
