"""
Result Ranker
=============

Combines multiple independent scoring signals into a single composite
score for each candidate file, then returns the top-N results.

Scoring signals
---------------
1. **Semantic similarity**  — cosine similarity between the query embedding
   and the stored file embedding (weight: 0.45).
2. **BM25**                 — keyword-level retrieval score (weight: 0.25).
3. **Filename similarity**  — fuzzy match between query tokens and filename
   (weight: 0.15).
4. **Folder similarity**    — fuzzy match between query tokens and folder name
   (weight: 0.05).
5. **Recency boost**        — files modified within the past year get a small
   bonus (weight: 0.10).

The BM25 implementation uses ``rank_bm25`` if installed, with a fallback
to simple TF (term frequency) scoring.
"""

from __future__ import annotations

import difflib
import logging
import re
import time
from typing import List, Optional

import numpy as np

from agentic.document_search.schemas import IndexedFile, SearchResult
from agentic.document_search.embeddings import (
    blob_to_vector,
    cosine_similarity,
    extract_keywords,
    generate_embedding,
)

logger = logging.getLogger(__name__)

# ── Weights ────────────────────────────────────────────────────────────────
W_SEMANTIC  = 0.45
W_BM25      = 0.25
W_FILENAME  = 0.15
W_FOLDER    = 0.05
W_RECENCY   = 0.10

TOP_N = 5
RECENCY_WINDOW_SECONDS = 365 * 24 * 3600  # 1 year


# ── BM25 helpers ───────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def _build_bm25_scores(query_tokens: list[str], corpus_keywords: list[str]) -> list[float]:
    """BM25 scoring with rank_bm25 library if available, else TF fallback."""
    if not query_tokens:
        return [0.0] * len(corpus_keywords)

    # Split each document's keyword string into a token list
    tokenized_corpus = [kw.split() for kw in corpus_keywords]

    try:
        from rank_bm25 import BM25Okapi
        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(query_tokens)
        # Normalise to [0, 1]
        max_score = float(np.max(scores)) if len(scores) > 0 else 1.0
        if max_score == 0:
            return [0.0] * len(corpus_keywords)
        return [float(s) / max_score for s in scores]
    except ImportError:
        # Simple TF fallback
        query_set = set(query_tokens)
        result = []
        for tokens in tokenized_corpus:
            if not tokens:
                result.append(0.0)
                continue
            overlap = sum(1 for t in tokens if t in query_set)
            result.append(overlap / len(tokens))
        return result


# ── Filename / folder similarity ───────────────────────────────────────────

def _filename_score(query_lower: str, filename: str) -> float:
    """SequenceMatcher ratio between lowercased query and filename stem."""
    stem = filename.rsplit(".", 1)[0].lower().replace("_", " ").replace("-", " ")
    return difflib.SequenceMatcher(None, query_lower, stem).ratio()


def _folder_score(query_lower: str, folder: str) -> float:
    """SequenceMatcher ratio between query and folder name."""
    folder_norm = folder.lower().replace("_", " ").replace("-", " ")
    return difflib.SequenceMatcher(None, query_lower, folder_norm).ratio()


# ── Recency score ──────────────────────────────────────────────────────────

def _recency_score(modified_ts: float) -> float:
    """Return 1.0 for very recent files, decaying to 0.0 for old files."""
    age = time.time() - modified_ts
    if age <= 0:
        return 1.0
    if age >= RECENCY_WINDOW_SECONDS:
        return 0.0
    return 1.0 - (age / RECENCY_WINDOW_SECONDS)


# ── Confidence label ───────────────────────────────────────────────────────

def _confidence_label(score: float) -> str:
    if score >= 0.7:
        return "high"
    elif score >= 0.45:
        return "medium"
    return "low"


# ── Main ranking function ──────────────────────────────────────────────────

def rank_results(
    query: str,
    candidates: List[IndexedFile],
    top_n: int = TOP_N,
) -> List[SearchResult]:
    """Rank ``candidates`` against ``query`` and return the top ``top_n`` results.

    Parameters
    ----------
    query:
        Raw user query string.
    candidates:
        List of :class:`IndexedFile` objects loaded from the cache.
    top_n:
        Maximum number of results to return (default 5).

    Returns
    -------
    list[SearchResult]
        Ranked results, best match first.
    """
    if not candidates:
        return []

    query_lower = query.lower()
    query_tokens = _tokenize(query)

    # ── 1. Query embedding ─────────────────────────────────────────────────
    query_embedding_blob = generate_embedding(query)
    query_vec: Optional[np.ndarray] = blob_to_vector(query_embedding_blob) if query_embedding_blob else None

    # ── 2. BM25 over all keyword strings ──────────────────────────────────
    corpus_keywords = [f.keywords for f in candidates]
    bm25_scores = _build_bm25_scores(query_tokens, corpus_keywords)

    # ── 3. Per-file scoring ────────────────────────────────────────────────
    scored: list[tuple[float, int]] = []

    for idx, f in enumerate(candidates):
        # Semantic
        if query_vec is not None and f.embedding_blob:
            file_vec = blob_to_vector(f.embedding_blob)
            sem = cosine_similarity(query_vec, file_vec) if file_vec is not None else 0.0
        else:
            sem = 0.0

        # BM25
        bm = bm25_scores[idx]

        # Filename
        fn = _filename_score(query_lower, f.filename)

        # Folder
        fo = _folder_score(query_lower, f.folder)

        # Recency
        rec = _recency_score(f.modified_ts)

        # Composite
        composite = (
            W_SEMANTIC * sem
            + W_BM25    * bm
            + W_FILENAME * fn
            + W_FOLDER   * fo
            + W_RECENCY  * rec
        )

        scored.append((composite, idx))

    # ── 4. Sort descending and take top_n ─────────────────────────────────
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_n]

    results: List[SearchResult] = []
    for rank, (score, idx) in enumerate(top, start=1):
        f = candidates[idx]
        snippet = f.summary or f.sample_text[:120]

        results.append(SearchResult(
            rank=rank,
            score=score,
            path=f.path,
            filename=f.filename,
            extension=f.extension,
            folder=f.folder,
            modified_ts=f.modified_ts,
            confidence=_confidence_label(score),
            snippet=snippet,
        ))

    return results
