"""
debug_typing.py
===============
Test typing using EM_REPLACESEL Win32 message.
"""
import sys
import time
import ctypes

sys.path.insert(0, r"d:\ai voice assisstant")
from automation.notepad import _controller

def get_edit_content(hwnd):
    edit_hwnd = _controller._find_edit_control(hwnd)
    if not edit_hwnd:
        return "NO_EDIT_CONTROL"
    buf = ctypes.create_unicode_buffer(1024)
    # WM_GETTEXT is 0x000D
    ctypes.windll.user32.SendMessageW(edit_hwnd, 0x000D, 1024, buf)
    return buf.value

def run():
    print("[DEBUG] Killing existing Notepad instances...")
    import subprocess
    subprocess.run(["taskkill", "/f", "/im", "notepad.exe"], capture_output=True)
    time.sleep(0.5)

    print("[DEBUG] Opening Notepad...")
    _controller.open_notepad()
    time.sleep(1.0)

    hwnd = _controller.find_notepad_hwnd()
    if not hwnd:
        print("[DEBUG] FATAL: Notepad HWND not found!")
        return

    edit_hwnd = _controller._find_edit_control(hwnd)
    print(f"[DEBUG] Notepad HWND={hwnd}, Edit HWND={edit_hwnd}")
    if not edit_hwnd:
        print("[DEBUG] FATAL: Edit control not found!")
        return

    # Clear first
    ctypes.windll.user32.SendMessageW(edit_hwnd, 0x000C, 0, "") # WM_SETTEXT with empty string
    
    initial_text = get_edit_content(hwnd)
    print(f"[DEBUG] Initial text: '{initial_text}'")

    print("[DEBUG] Sending EM_REPLACESEL with 'EM_REPLACESEL_WORKS'...")
    # EM_REPLACESEL is 0x00C2
    # wParam: Can Undo (True/1)
    # lParam: LPCWSTR text
    res = ctypes.windll.user32.SendMessageW(edit_hwnd, 0x00C2, 1, "EM_REPLACESEL_WORKS")
    print(f"[DEBUG] SendMessageW(EM_REPLACESEL) result: {res}")
    time.sleep(0.5)

    typed_text = get_edit_content(hwnd)
    print(f"[DEBUG] Text after EM_REPLACESEL: '{typed_text}'")

    if "EM_REPLACESEL_WORKS" in typed_text:
        print("[DEBUG] SUCCESS: EM_REPLACESEL successfully inserted the text!")
    else:
        print("[DEBUG] FAILURE: EM_REPLACESEL did not work.")

if __name__ == "__main__":
    run()
