"""
agentic/document_search
=======================

AI-powered context-based file finder.

This package provides semantic document search across local drives.
It is a self-contained plugin — nothing outside this package is modified
except for three registration lines in the execution layer.

Public API:
    from agentic.document_search.manager import DocumentSearchManager
    results = DocumentSearchManager.find_documents("CDOT proposal from last year")
"""
