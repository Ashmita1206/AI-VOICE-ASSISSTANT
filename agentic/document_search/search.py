"""
Context Document Search — High-Level API
==========================================

Provides the ``ContextDocumentSearch`` class as the main search entry
point, bridging the indexer, cache, and ranker.
"""

from __future__ import annotations

import logging
from typing import List

from agentic.document_search import cache
from agentic.document_search.ranking import rank_results
from agentic.document_search.schemas import SearchResult

logger = logging.getLogger(__name__)


class ContextDocumentSearch:
    """High-level search API consumed by the tool handler.

    This class is stateless — it delegates everything to the cache
    and ranker. The indexer is managed separately by the manager.

    Usage::

        searcher = ContextDocumentSearch()
        results = searcher.search("CDOT proposal from last year")
    """

    def search(self, query: str, top_n: int = 5) -> List[SearchResult]:
        """Perform a semantic context search against the local document index.

        Parameters
        ----------
        query:
            Free-form user description (e.g. "my CDOT proposal from 2021").
        top_n:
            Maximum number of results to return.

        Returns
        -------
        list[SearchResult]
            Ranked list of best-matching files, best match first.
        """
        if not query or not query.strip():
            logger.warning("[SEARCH] Empty query received.")
            return []

        total = cache.get_indexed_count()
        logger.info("[SEARCH] Query: %r  |  Index size: %d files", query, total)

        if total == 0:
            logger.info("[SEARCH] Index is empty — returning no results.")
            return []

        # Load all files with embeddings
        candidates = cache.get_all_files(with_embeddings=True)

        # Rank candidates
        results = rank_results(query, candidates, top_n=top_n)
        logger.info("[SEARCH] Returning %d result(s) for query: %r", len(results), query)
        return results
