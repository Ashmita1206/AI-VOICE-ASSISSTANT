"""
Context Document Search — High-Level API
==========================================

Provides the ``ContextDocumentSearch`` class as the main search entry
point, bridging the indexer, cache, and ranker.
"""

from __future__ import annotations

import logging
import os
import time
from typing import List

from agentic.file_context_search import cache
from agentic.file_context_search.ranking import rank_results, extract_target_tokens, normalize_compact, EXCLUDED_EXTENSIONS
from agentic.file_context_search.schemas import SearchResult, IndexedFile
from agentic.file_context_search.scanner import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

KNOWN_PROJECT_ROOTS = [
    r"D:\HEALTHSPHERE",
    r"D:\healthsphere content",
    r"D:\MONEY MENTOR",
    r"D:\moneymentor",
    r"D:\moneymentor content",
]


def _ensure_project_indexed_on_demand(query: str, project_folders: list[str] | None = None) -> None:
    """Scan and index matching target project folders on demand if mentioned in query."""
    norm_query = normalize_compact(query)
    target_roots: list[str] = list(project_folders) if project_folders else []

    for root in KNOWN_PROJECT_ROOTS:
        norm_root = normalize_compact(root)
        if ("healthsphere" in norm_query and "healthsphere" in norm_root) or \
           (("money" in norm_query or "mentor" in norm_query) and ("money" in norm_root or "mentor" in norm_root)):
            if os.path.exists(root) and root not in target_roots:
                target_roots.append(root)

    if not target_roots:
        return

    logger.info("[SEARCH] Dynamic scan triggered for project roots: %s", target_roots)
    
    for root_dir in target_roots:
        indexed_count = 0
        ignored_count = 0
        logger.info("[RECURSIVE SCAN START] Scanning target root: %s", root_dir)
        for dirpath, dirnames, filenames in os.walk(root_dir):
            # Exclude build and noise dirs
            original_dirs = list(dirnames)
            dirnames[:] = [d for d in dirnames if d.lower() not in ["node_modules", ".git", "__pycache__", "venv", ".venv", "dist", "build", ".next", "uv\\cache", "$recycle.bin"]]
            ignored_dirs = set(original_dirs) - set(dirnames)
            
            logger.info("[RECURSIVE SCAN] Visited folder: %s | Subfolders: %s | Ignored folders: %s | Files count: %d",
                        dirpath, dirnames, list(ignored_dirs), len(filenames))
            
            for filename in filenames:
                ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                full_path = os.path.join(dirpath, filename)
                
                if ext not in SUPPORTED_EXTENSIONS or ext in EXCLUDED_EXTENSIONS:
                    ignored_count += 1
                    logger.debug("[RECURSIVE SCAN] Ignored source/system file: %s", full_path)
                    continue
                
                if not os.path.exists(full_path):
                    ignored_count += 1
                    continue
                
                try:
                    stat = os.stat(full_path)
                    idx_file = IndexedFile(
                        path=full_path,
                        filename=filename,
                        extension=ext,
                        size_bytes=stat.st_size,
                        modified_ts=stat.st_mtime,
                        folder=os.path.basename(dirpath),
                        folder_path=dirpath,
                        sample_text="",
                        keywords=f"{filename} {os.path.basename(dirpath)}",
                        summary="",
                    )
                    cache.upsert_file(idx_file)
                    indexed_count += 1
                    logger.info("[RECURSIVE SCAN] Indexed file: %s", full_path)
                except Exception as e:
                    logger.warning("[RECURSIVE SCAN] Could not index %s: %s", full_path, e)

        logger.info("[RECURSIVE SCAN COMPLETE] Root: %s | Total User Document Candidates: %d | Ignored Source Files: %d",
                    root_dir, indexed_count, ignored_count)


from agentic.file_context_search.project_discovery import discover_project_folders


class ContextDocumentSearch:
    """High-level search API consumed by the tool handler (Project-Centric Architecture)."""

    def search(self, query: str, top_n: int = 5) -> List[SearchResult]:
        if not query or not query.strip():
            logger.warning("[SEARCH] Empty query received.")
            return []

        logger.info("==========================================================")
        logger.info("[PROJECT-CENTRIC PIPELINE] Query: %r", query)
        logger.info("==========================================================")

        # 1. PROJECT FOLDER DISCOVERY (Step 1)
        matched_project_folders = discover_project_folders(query)
        logger.info("[PROJECT DISCOVERY] Matched %d project folder(s): %s",
                    len(matched_project_folders), matched_project_folders)

        # 2. ENSURE DISCOVERED PROJECT FOLDERS ARE INDEXED (Step 2)
        _ensure_project_indexed_on_demand(query, matched_project_folders)

        # 3. COLLECT CANDIDATE DOCUMENTS (Step 2 & Step 6)
        all_candidates = cache.get_all_files(with_embeddings=False)
        
        # If project folders were discovered, restrict candidates strictly to those project folders!
        if matched_project_folders:
            project_candidates = []
            for c in all_candidates:
                c_path_norm = os.path.normpath(c.path).lower()
                for pf in matched_project_folders:
                    pf_norm = os.path.normpath(pf).lower()
                    if c_path_norm.startswith(pf_norm):
                        project_candidates.append(c)
                        break
            
            logger.info("[PROJECT CANDIDATES] Filtered candidates to %d files inside matched project folders",
                        len(project_candidates))
            candidates = project_candidates if project_candidates else all_candidates
        else:
            candidates = all_candidates

        # 4. RANK CANDIDATES (Step 3, 4 & 5)
        results = rank_results(query, candidates, top_n=top_n, project_folder_candidates=matched_project_folders)
        logger.info("[PROJECT-CENTRIC PIPELINE COMPLETE] Returning %d result(s) for query: %r",
                    len(results), query)
        return results
