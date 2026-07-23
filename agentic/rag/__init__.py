"""
LangChain RAG Package
=====================

Exposes existing local context RAG as a LangChain BaseRetriever.
Does NOT replace or alter existing RAG search/indexing algorithms.
"""

from agentic.rag.langchain_wrapper import LangChainRAGRetriever

__all__ = ["LangChainRAGRetriever"]
