"""
Resource Schemas
================

Data structures representing discovered desktop resources (apps, URLs, files, etc.).
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

@dataclass
class Resource:
    name: str
    type: str  # "application", "website", "file", "folder", "process"
    source: str  # "registry", "start_menu", "desktop", "browser_bookmark", "browser_history", "filesystem", "running_process"
    confidence: float = 1.0
    
    # Details based on type
    executable: Optional[str] = None
    url: Optional[str] = None
    path: Optional[str] = None
    pid: Optional[int] = None
    
    # Enhanced resource fields
    last_used: float = 0.0
    is_running: bool = False
    install_location: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict, filtering out None values."""
        # Make sure boolean is_running and float last_used are preserved even if they look like falsy/empty values
        d = {k: v for k, v in asdict(self).items() if v is not None}
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Resource":
        """Instantiate from dict."""
        return cls(
            name=data["name"],
            type=data["type"],
            source=data["source"],
            confidence=data.get("confidence", 1.0),
            executable=data.get("executable"),
            url=data.get("url"),
            path=data.get("path"),
            pid=data.get("pid"),
            last_used=data.get("last_used", 0.0),
            is_running=data.get("is_running", False),
            install_location=data.get("install_location"),
        )
