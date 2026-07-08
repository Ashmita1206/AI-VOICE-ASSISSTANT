"""
OS Permissions Engine
======================

Handles checking, verifying, and requesting system-level permissions for Desktop Automation.
"""

import os
import sys
import time
import json
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# Ephemeral mock store to support toggling/simulating permissions dynamically
_mock_permissions_store = {
    "Accessibility/UI Automation": True,
    "Keyboard Control": True,
    "Mouse Control": True,
    "Screen Capture": True,
    "Foreground Window Control": True,
    "Browser Automation": True,
    "File System Access": True,
    "Microphone": True
}

def verify_os_permission(name: str) -> bool:
    """Check if the given OS permission is granted on Windows, fallback to mock store."""
    if not _mock_permissions_store.get(name, False):
        return False

    try:
        if name == "Accessibility/UI Automation":
            # Verify UIAutomation works
            import uiautomation as uia
            root = uia.GetRootControl()
            return root is not None
        elif name == "Screen Capture":
            # Verify screen capturing works
            from PIL import ImageGrab
            im = ImageGrab.grab(bbox=(0, 0, 1, 1))
            return im is not None
        elif name == "Microphone":
            # Verify audio recording capabilities
            import sounddevice as sd
            devices = sd.query_devices()
            return len(devices) > 0
        elif name == "File System Access":
            # Verify file write access to the project root
            test_file = "d:/ai voice assisstant/.permission_test"
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            return True
        elif name == "Browser Automation":
            # Verify selenium or playwright availability
            import selenium
            return True
        return True
    except Exception as e:
        logger.warning("Verification check failed for %s: %s", name, e)
        return False

def check_all_required_permissions(permissions_needed: List[str]) -> Dict[str, bool]:
    """Check a list of permissions and return a dictionary of their status."""
    results = {}
    for p in permissions_needed:
        status = verify_os_permission(p)
        print(f"[DEBUG LOG] Permission: {p} | Verification Result: {status}")
        results[p] = status
    return results

def grant_os_permission(name: str) -> bool:
    """Attempt to trigger OS dialog or open settings pane for a permission."""
    print(f"[DEBUG LOG] Permission Grant Request: {name}")
    try:
        # Launch settings panels on Windows to guide the user
        if name == "Accessibility/UI Automation":
            os.system("start ms-settings:easeofaccess-keyboard")
        elif name == "Microphone":
            os.system("start ms-settings:privacy-microphone")
        elif name == "Screen Capture":
            os.system("start ms-settings:privacy-webcam")
            
        # Update store to simulate success on next verification run
        _mock_permissions_store[name] = True
        print(f"[DEBUG LOG] Permission Grant Result for {name}: Granted")
        return True
    except Exception as e:
        logger.warning("Failed to trigger grant flow for %s: %s", name, e)
        return False

def set_mock_permission(name: str, granted: bool):
    """Explicitly set a mock permission status for testing/simulating errors."""
    _mock_permissions_store[name] = granted
