"""
Document Retrieval Schemas
==========================

Data contracts for the document retrieval engine.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import datetime

@dataclass
class IndexedDocument:
    """Represents a document stored in the index (SQLite + FAISS)."""
    id: int  # SQLite primary key, used as FAISS ID
    path: str
    filename: str
    folder: str
    extension: str
    size_bytes: int
    modified_ts: float
    summary: str
    entities_json: str
    keywords: str
    parent_folder: str = ""
    project_folder: str = ""
    relative_path: str = ""
    content_hash: str = ""
    last_indexed: float = 0.0
    
    # Internal representation of the vector (not typically stored back in this struct once in FAISS)
    embedding: Optional[Any] = None

@dataclass
class SearchResult:
    """A ranked result returned to the caller."""
    rank: int
    score: float
    path: str
    filename: str
    extension: str
    folder: str
    modified_ts: float
    confidence_pct: int
    snippet: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API responses and frontend display."""
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
            "confidence_pct": self.confidence_pct,
            "snippet": self.snippet,
        }

@dataclass
class IndexerStatus:
    """Status of the background indexing engine."""
    is_running: bool
    is_ready: bool
    indexed_count: int
    last_scan: float
    is_watching: bool
