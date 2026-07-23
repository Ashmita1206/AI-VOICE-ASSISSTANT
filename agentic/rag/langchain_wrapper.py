"""
LangChain BaseRetriever Wrapper for Existing RAG Engine
======================================================

Wraps DocumentSearchManager / file_context_search as a LangChain BaseRetriever.
Reuses existing BM25 + FAISS + Dense Embedding RAG pipeline without modifying it.
"""

from __future__ import annotations
import logging
from typing import Any, List
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from pydantic import Field

logger = logging.getLogger("agentic.rag.langchain_wrapper")


class LangChainRAGRetriever(BaseRetriever):
    """LangChain Retriever wrapper over existing local context RAG engine."""

    top_n: int = Field(default=5)

    def _get_relevant_documents(self, query: str, *, run_manager: Any = None) -> List[Document]:
        """Retrieve relevant context documents using existing DocumentSearchManager."""
        logger.info("[LANGCHAIN RAG] Querying existing RAG engine query='%s' top_n=%d", query, self.top_n)

        try:
            from agentic.file_context_search.manager import DocumentSearchManager
            results = DocumentSearchManager.find_documents(query, top_n=self.top_n)

            docs: List[Document] = []
            for r in results:
                content = r.snippet or f"Document: {r.filename} in {r.folder}"
                metadata = {
                    "rank": r.rank,
                    "score": r.score,
                    "path": r.path,
                    "filename": r.filename,
                    "extension": r.extension,
                    "folder": r.folder,
                    "confidence": r.confidence,
                }
                docs.append(Document(page_content=content, metadata=metadata))

            logger.info("[LANGCHAIN RAG] Retrieved %d documents from existing RAG", len(docs))
            return docs
        except Exception as e:
            logger.exception("[LANGCHAIN RAG] Failed to query existing RAG engine: %s", e)
            return []
