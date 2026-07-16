"""
Document Search Schemas
=======================

Data contracts for the AI-powered context-based file finder.
All dataclasses are pure Python — no external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class IndexedFile:
    """Represents a single file stored in the local document index.

    Attributes
    ----------
    path:
        Absolute path to the file on disk.
    filename:
        Basename of the file (e.g. ``Proposal_Final_v3.docx``).
    extension:
        Lowercase extension without dot (e.g. ``docx``).
    size_bytes:
        File size in bytes.
    modified_ts:
        Last-modified timestamp (Unix epoch float).
    folder:
        Parent directory name (not full path).
    folder_path:
        Full parent directory path.
    sample_text:
        First ~2000 characters of extracted content.
    keywords:
        Space-separated keyword tokens extracted from content.
    summary:
        Short auto-generated summary (first meaningful sentence(s)).
    embedding_blob:
        Raw bytes of the float32 numpy array (stored as BLOB in SQLite).
    """

    path: str
    filename: str
    extension: str
    size_bytes: int = 0
    modified_ts: float = 0.0
    folder: str = ""
    folder_path: str = ""
    sample_text: str = ""
    keywords: str = ""
    summary: str = ""
    embedding_blob: Optional[bytes] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dict (excluding binary blob)."""
        return {
            "path": self.path,
            "filename": self.filename,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "modified_ts": self.modified_ts,
            "folder": self.folder,
            "folder_path": self.folder_path,
            "summary": self.summary,
            "keywords": self.keywords,
        }


@dataclass
class SearchResult:
    """A single ranked result returned from a context search.

    Attributes
    ----------
    rank:
        1-based position in the result list (1 = best match).
    score:
        Composite ranking score in [0.0, 1.0].
    path:
        Absolute path to the matched file.
    filename:
        Basename of the matched file.
    extension:
        File extension (without dot).
    folder:
        Parent folder name.
    modified_ts:
        Last-modified timestamp (Unix epoch float).
    confidence:
        Human-readable confidence label (``"high"`` / ``"medium"`` / ``"low"``).
    snippet:
        Short text excerpt from the file content.
    """

    rank: int
    score: float
    path: str
    filename: str
    extension: str
    folder: str
    modified_ts: float
    confidence: str = "medium"
    snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dict for API responses."""
        import datetime
        try:
            mod_date = datetime.datetime.fromtimestamp(self.modified_ts).strftime("%Y-%m-%d")
        except Exception:
            mod_date = "unknown"

        return {
            "rank": self.rank,
            "score": round(self.score, 4),
            "path": self.path,
            "filename": self.filename,
            "extension": self.extension,
            "folder": self.folder,
            "modified_date": mod_date,
            "confidence": self.confidence,
            "snippet": self.snippet,
        }

    def voice_label(self) -> str:
        """Return a short label suitable for TTS (e.g., 'Proposal_Final_v3 dot docx')."""
        import datetime
        try:
            mod_date = datetime.datetime.fromtimestamp(self.modified_ts).strftime("%b %Y")
        except Exception:
            mod_date = ""
        ext_spoken = self.extension.upper() if self.extension else ""
        parts = [self.filename]
        if ext_spoken:
            parts.append(f"({ext_spoken})")
        if self.folder:
            parts.append(f"in {self.folder}")
        if mod_date:
            parts.append(f"— {mod_date}")
        return " ".join(parts)
