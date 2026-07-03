"""
Tests for Automation Tools
"""

import os
from pathlib import Path
from agentic.automation.filesystem import create_file, delete_file

def test_filesystem_create_delete():
    # Test file creation
    test_file = "~/test_voice_assistant_file.txt"
    res1 = create_file({"path": test_file})
    assert res1.success
    
    path = Path(test_file).expanduser()
    assert path.exists()
    
    # Test file deletion
    res2 = delete_file({"path": test_file})
    assert res2.success
    assert not path.exists()
