"""
capture_notepad.py
==================
Capture screenshot of Notepad window and print diagnostics.
"""
import sys
import time
import pyperclip
from PIL import ImageGrab

sys.path.insert(0, r"d:\ai voice assisstant")
from automation.notepad import _controller

def run():
    # 1. Open Notepad
    _controller.open_notepad()
    time.sleep(1.0)
    
    # 2. Type text
    _controller.type_text("SCREENSHOT_TEST_HELLO_WORLD")
    time.sleep(1.0)
    
    # 3. Get window rect and take screenshot
    hwnd = _controller.find_notepad_hwnd()
    if hwnd:
        import win32gui
        rect = win32gui.GetWindowRect(hwnd)
        print(f"[CAPTURE] Notepad window rect: {rect}")
        # Crop to rect
        im = ImageGrab.grab(bbox=rect)
        im.save(r"C:\Users\HP\.gemini\antigravity-ide\brain\1e433aec-6443-4993-bbbf-1c6daa2cc832\notepad_screenshot.png")
        print("[CAPTURE] Screenshot saved to artifacts as notepad_screenshot.png")
        
        # Now copy and check content
        _controller.select_all()
        time.sleep(0.2)
        _controller.copy()
        time.sleep(0.5)
        content = pyperclip.paste().strip()
        print(f"[CAPTURE] Clipboard content: '{content}'")
    else:
        print("[CAPTURE] Notepad window not found!")

if __name__ == "__main__":
    run()
