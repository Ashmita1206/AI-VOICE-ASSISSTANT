"""
Document Search Tool Handler
==============================

Delegates to document_retrieval_tool for unified handling.
"""

from typing import Any
from execution.schemas import ExecutionResult
from automation.document_retrieval_tool import find_document_by_context, open_document_result

__all__ = ["find_document_by_context", "open_document_result"]
