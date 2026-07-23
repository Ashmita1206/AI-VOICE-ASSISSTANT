"""
Document Retrieval Package
===========================

Production-grade semantic document retrieval engine for the AI Voice Assistant.
Searches local files using FAISS vector similarity, BM25 keyword matching,
entity overlap, and multi-signal ranking.

Usage::

    from agentic.document_retrieval.manager import DocumentRetrievalManager

    DocumentRetrievalManager.start_indexer()
    results = DocumentRetrievalManager.find_documents("HealthSphere proposal")
"""

from agentic.document_retrieval.manager import DocumentRetrievalManager

__all__ = ["DocumentRetrievalManager"]
