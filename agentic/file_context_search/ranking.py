"""
Result Ranker — Phase 14 Robust Matching Engine
=================================================

Combines robust case-insensitive, space/punctuation normalized, partial,
token-based, fuzzy, folder-prioritized, BM25, and semantic scoring signals.

Ranking Hierarchy
-----------------
1. Folder name match (highest)
2. Filename token / partial match
3. Token overlap & Fuzzy similarity
4. BM25 keyword matching
5. Semantic similarity

System noise (AppData, Windows, MSYS, node_modules, .next, etc.) and non-existent
files (os.path.exists == False) are strictly filtered out.
"""

from __future__ import annotations

import difflib
import logging
import os
import re
import time
from typing import List, Optional

import numpy as np

from agentic.file_context_search.schemas import IndexedFile, SearchResult
from agentic.file_context_search.embeddings import (
    blob_to_vector,
    cosine_similarity,
    extract_keywords,
    generate_embedding,
)

logger = logging.getLogger(__name__)

# ── Weights & Settings ──────────────────────────────────────────────────────
W_FOLDER    = 0.35
W_FILENAME  = 0.35
W_TOKEN     = 0.15
W_BM25      = 0.10
W_SEMANTIC  = 0.05

TOP_N = 5
RECENCY_WINDOW_SECONDS = 365 * 24 * 3600  # 1 year

DOC_TYPE_HIERARCHY: dict[str, float] = {
    "pdf": 1.2,
    "ppt": 1.0,
    "pptx": 1.0,
    "odp": 1.0,
    "doc": 0.8,
    "docx": 0.8,
    "odt": 0.8,
    "xls": 0.7,
    "xlsx": 0.7,
    "csv": 0.7,
    "ods": 0.7,
    "txt": 0.5,
    "rtf": 0.5,
    "png": 0.3,
    "jpg": 0.3,
    "jpeg": 0.3,
    "svg": 0.2,
    "webp": 0.2,
    "ipynb": 0.4,
    "md": 0.1,
}

STOP_WORDS = frozenset({
    "open", "search", "find", "for", "the", "document", "file", "explorer",
    "in", "from", "a", "an", "of", "and", "or", "to", "with", "my", "please"
})

NOISE_PATH_FRAGMENTS = (
    "\\appdata\\",
    "\\windows\\",
    "\\msys",
    "\\program files",
    "\\node_modules\\",
    "\\.next\\",
    "\\.venv\\",
    "\\venv\\",
    "\\site-packages\\",
    "\\uv\\cache\\",
    "\\.git\\",
    "\\__pycache__\\",
    "\\$recycle.bin\\",
    "$recycle.bin",
    "\\.cursor\\",
    "\\.vscode\\",
    "\\.idea\\",
)


# ── Normalization Helpers ──────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """Normalize text: lowercase, strip punctuation/special chars, collapse spaces."""
    if not text:
        return ""
    cleaned = re.sub(r"[_\-\.\(\)\[\]\{\}/\\,;:!?'\"`@#$%^&*+=<>~]", " ", text.lower())
    return " ".join(cleaned.split())


def normalize_compact(text: str) -> str:
    """Return compact alphanumeric lowercase string (e.g. 'moneymentor')."""
    if not text:
        return ""
    return re.sub(r"[^a-zA-Z0-9]", "", text.lower())


def extract_target_tokens(query: str) -> list[str]:
    """Extract non-stopword target tokens from user query."""
    norm = normalize_text(query)
    tokens = norm.split()
    targets = [t for t in tokens if t not in STOP_WORDS]
    return targets if targets else tokens


EXCLUDED_EXTENSIONS = frozenset({
    "py", "js", "ts", "jsx", "tsx", "java", "cpp", "c", "h", "cs", "go", "rb",
    "php", "swift", "kt", "rs", "sh", "bat", "ps1", "html", "htm", "css", "xml",
    "dll", "exe", "pyd", "so", "class", "pyc", "obj", "bin", "sys"
})


def is_valid_file(file_path: str) -> bool:
    """Check physical existence and exclude system/noise paths and source code extensions."""
    if not file_path or not os.path.exists(file_path):
        return False
    
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    if ext in EXCLUDED_EXTENSIONS:
        return False
        
    norm_path = file_path.lower()
    for frag in NOISE_PATH_FRAGMENTS:
        if frag.lower() in norm_path:
            return False
    return True


# ── Scoring Signals ────────────────────────────────────────────────────────

def _folder_score(target_tokens: list[str], target_compact: str, folder_path: str) -> float:
    """Score folder match quality."""
    if not folder_path:
        return 0.0
    
    folder_norm = normalize_text(folder_path)
    folder_compact = normalize_compact(folder_path)
    
    # Extract directory names along path
    dirs_compact = [normalize_compact(d) for d in folder_path.replace("/", "\\").split("\\") if d]
    
    # 1. Directory name match (e.g. directory 'HEALTHSPHERE', 'healthsphere content', 'moneymentor')
    if target_compact and any(target_compact in d for d in dirs_compact):
        return 1.5
    
    # 2. Substring phrase match in directory path
    if target_compact and len(target_compact) > 3 and target_compact in folder_compact:
        return 1.2
    
    # 3. Token match in folder path
    if target_tokens:
        matches = sum(1 for t in target_tokens if t in folder_norm or t in folder_compact)
        token_ratio = matches / len(target_tokens)
        if token_ratio == 1.0:
            return 0.8
        return token_ratio * 0.5
        
    return 0.0


def _filename_score(target_tokens: list[str], target_compact: str, filename: str) -> float:
    """Score filename match quality (case-insensitive, space/punct agnostic)."""
    if not filename:
        return 0.0
    
    stem = filename.rsplit(".", 1)[0]
    stem_norm = normalize_text(stem)
    stem_compact = normalize_compact(stem)
    
    # 1. Exact compact phrase match
    if target_compact and target_compact == stem_compact:
        return 1.0
    
    # 2. Substring phrase match
    if target_compact and len(target_compact) > 3 and target_compact in stem_compact:
        return 0.95
    
    # 3. All tokens present in filename stem
    if target_tokens:
        matches = sum(1 for t in target_tokens if t in stem_norm or t in stem_compact)
        if matches == len(target_tokens):
            return 0.90
        token_ratio = matches / len(target_tokens)
        return token_ratio * 0.6
        
    # 4. Fuzzy ratio fallback
    return difflib.SequenceMatcher(None, " ".join(target_tokens), stem_norm).ratio()


def _fuzzy_score(target_phrase: str, text: str) -> float:
    """Fuzzy sequence similarity."""
    norm_text = normalize_text(text)
    if not target_phrase or not norm_text:
        return 0.0
    return difflib.SequenceMatcher(None, target_phrase, norm_text).ratio()


def _build_bm25_scores(query_tokens: list[str], corpus_keywords: list[str]) -> list[float]:
    """BM25 scoring with rank_bm25 library if available, else TF fallback."""
    if not query_tokens:
        return [0.0] * len(corpus_keywords)

    tokenized_corpus = [kw.split() for kw in corpus_keywords]

    try:
        from rank_bm25 import BM25Okapi
        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(query_tokens)
        max_score = float(np.max(scores)) if len(scores) > 0 else 1.0
        if max_score == 0:
            return [0.0] * len(corpus_keywords)
        return [float(s) / max_score for s in scores]
    except ImportError:
        query_set = set(query_tokens)
        result = []
        for tokens in tokenized_corpus:
            if not tokens:
                result.append(0.0)
                continue
            overlap = sum(1 for t in tokens if t in query_set)
            result.append(overlap / len(tokens))
        return result


def _confidence_label(score: float) -> str:
    if score >= 0.7:
        return "high"
    elif score >= 0.45:
        return "medium"
    return "low"


# ── Main Ranking Function ──────────────────────────────────────────────────

def rank_results(
    query: str,
    candidates: List[IndexedFile],
    top_n: int = TOP_N,
    project_folder_candidates: list[str] | None = None,
) -> List[SearchResult]:
    """Rank candidates against query using production-grade matching & scoring rules."""
    if not candidates or not query or not query.strip():
        return []

    # 1. Extract target query representation
    target_tokens = extract_target_tokens(query)
    target_compact = normalize_compact(" ".join(target_tokens))
    target_phrase = " ".join(target_tokens)
    query_tokens = target_tokens

    # 2. Filter candidates for disk existence & noise exclusion
    valid_candidates: list[IndexedFile] = []
    for cand in candidates:
        if is_valid_file(cand.path):
            valid_candidates.append(cand)

    if not valid_candidates:
        logger.warning("[RANKING] No valid candidates remaining after noise/existence filtering.")
        return []

    # Use all valid candidates — search.py already pre-filters to project folders
    # Pre-filter by token match in path or filename to avoid scoring unrelated files
    token_matched = [
        c for c in valid_candidates
        if any(t in c.path.lower() for t in target_tokens)
    ]
    corpus_candidates = token_matched if token_matched else valid_candidates

    # 3. Query embedding & BM25
    query_embedding_blob = generate_embedding(query)
    query_vec: Optional[np.ndarray] = blob_to_vector(query_embedding_blob) if query_embedding_blob else None

    corpus_keywords = [c.keywords for c in corpus_candidates]
    bm25_scores = _build_bm25_scores(query_tokens, corpus_keywords)

    # 4. Score each candidate
    has_primary_docs = any(f.extension.lower() in ("pdf", "ppt", "pptx", "doc", "docx", "xls", "xlsx") for f in corpus_candidates)
    scored_items: list[tuple[float, float, float, float, float, float, IndexedFile]] = []

    for idx, f in enumerate(corpus_candidates):
        # Folder Score
        fo_score = _folder_score(target_tokens, target_compact, f.path)

        # Filename Score
        fn_score = _filename_score(target_tokens, target_compact, f.filename)

        # Token Score
        tk_score = _fuzzy_score(target_phrase, f.filename)

        # BM25 Score
        bm_score = bm25_scores[idx]

        # Semantic Score
        if query_vec is not None and f.embedding_blob:
            file_vec = blob_to_vector(f.embedding_blob)
            sem_score = cosine_similarity(query_vec, file_vec) if file_vec is not None else 0.0
        else:
            sem_score = 0.0

        # Document Type Hierarchy Weighting
        ext_lower = f.extension.lower()
        doc_hierarchy_score = DOC_TYPE_HIERARCHY.get(ext_lower, 0.0)

        # Extension Query Match Boost
        ext_boost = 0.0
        q_norm = query.lower()
        if "pdf" in q_norm and ext_lower == "pdf":
            ext_boost = 1.0
        elif ("ppt" in q_norm or "presentation" in q_norm) and ext_lower in ("ppt", "pptx", "odp"):
            ext_boost = 1.0
        elif ("report" in q_norm or "doc" in q_norm) and ext_lower in ("pdf", "docx", "doc", "txt", "md"):
            ext_boost = 0.8
        elif ("excel" in q_norm or "spreadsheet" in q_norm) and ext_lower in ("xlsx", "xls", "csv"):
            ext_boost = 1.0

        # Composite Score
        composite = (
            W_FOLDER   * fo_score
          + W_FILENAME * fn_score
          + W_TOKEN    * tk_score
          + W_BM25     * bm_score
          + W_SEMANTIC * sem_score
          + doc_hierarchy_score
          + ext_boost
        )

        # Heavy boost if candidate is inside requested project folder
        if fo_score >= 0.9:
            composite += 1.5
        elif fn_score >= 0.9:
            composite += 0.8

        # Penalty for MD / JSON / Images / TXT when real documents exist
        if has_primary_docs and ext_lower not in ("pdf", "ppt", "pptx", "doc", "docx", "xls", "xlsx"):
            composite -= 5.0

        scored_items.append((composite, fo_score, fn_score, bm_score, sem_score, float(idx), f))

    # 5. Sort descending by composite score
    scored_items.sort(key=lambda x: x[0], reverse=True)

    # If project folder query specified, filter to top results matching project folder if available
    if project_folder_candidates:
        project_matched = [item for item in scored_items if item[1] >= 0.9]
        if project_matched:
            scored_items = project_matched

    top_items = scored_items[:top_n]

    results: List[SearchResult] = []
    for rank, (composite_score, fo, fn, bm, sem, idx, f) in enumerate(top_items, start=1):
        snippet = getattr(f, 'summary', '') or (f.sample_text[:120] if hasattr(f, 'sample_text') and f.sample_text else f.filename)
        
        logger.info(
            "[RANKING] #%d | Path: %s | FinalScore: %.3f | Folder: %.2f | Fn: %.2f | BM25: %.2f | Sem: %.2f",
            rank, f.path, composite_score, fo, fn, bm, sem
        )

        results.append(SearchResult(
            rank=rank,
            score=round(composite_score, 4),
            path=f.path,
            filename=f.filename,
            extension=f.extension,
            folder=f.folder,
            modified_ts=f.modified_ts,
            confidence=_confidence_label(composite_score),
            snippet=snippet,
        ))

    return results
