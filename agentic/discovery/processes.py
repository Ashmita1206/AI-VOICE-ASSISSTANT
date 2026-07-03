"""
Processes Scanner
=================

Scans for currently running processes on the system using psutil.
"""

import logging
from typing import List
from agentic.discovery.schemas import Resource

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger(__name__)

def scan_running_processes() -> List[Resource]:
    """Scan the system for running processes."""
    resources = []
    if not psutil:
        return resources
        
    seen_names = set()
    
    # Iterate over all running processes
    for proc in psutil.process_iter(attrs=['pid', 'name', 'exe']):
        try:
            name = proc.info.get('name')
            if not name:
                continue
                
            name_lower = name.lower()
            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)
            
            resources.append(Resource(
                name=name,
                type="process",
                source="running_process",
                pid=proc.info.get('pid'),
                executable=proc.info.get('exe'),
                confidence=0.95
            ))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        except Exception as e:
            logger.debug(f"Failed to scan process: {e}")
            
    return resources
