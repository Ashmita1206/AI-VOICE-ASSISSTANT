"""
debug_messages.py
================
Test various Win32 messages (Select All, Copy, Paste, Undo, Redo, Enter) on RichEditD2DPT.
"""
import sys
import time
import ctypes
import pyperclip

sys.path.insert(0, r"d:\ai voice assisstant")
from automation.notepad import _controller

def get_edit_content(hwnd):
    edit_hwnd = _controller._find_edit_control(hwnd)
    buf = ctypes.create_unicode_buffer(1024)
    ctypes.windll.user32.SendMessageW(edit_hwnd, 0x000D, 1024, buf)
    return buf.value

def run():
    print("[DEBUG] Killing existing Notepad...")
    import subprocess
    subprocess.run(["taskkill", "/f", "/im", "notepad.exe"], capture_output=True)
    time.sleep(0.5)

    _controller.open_notepad()
    time.sleep(1.0)
    hwnd = _controller.find_notepad_hwnd()
    edit_hwnd = _controller._find_edit_control(hwnd)
    print(f"[DEBUG] Notepad HWND={hwnd}, Edit HWND={edit_hwnd}")

    # Set initial text
    ctypes.windll.user32.SendMessageW(edit_hwnd, 0x000C, 0, "Line 1\r\nLine 2")
    print(f"[DEBUG] Initial text: {get_edit_content(hwnd)!r}")

    # 1. Test EM_SETSEL (Select All)
    # EM_SETSEL is 0x00B1. wParam = start, lParam = end. 0 and -1 selects all.
    res_sel = ctypes.windll.user32.SendMessageW(edit_hwnd, 0x00B1, 0, -1)
    print(f"[DEBUG] SendMessageW(EM_SETSEL) Select All result: {res_sel}")

    # 2. Test WM_COPY
    # WM_COPY is 0x0301.
    pyperclip.copy("CLEARED_CLIPBOARD")
    res_copy = ctypes.windll.user32.SendMessageW(edit_hwnd, 0x0301, 0, 0)
    time.sleep(0.2)
    clip_val = pyperclip.paste()
    print(f"[DEBUG] SendMessageW(WM_COPY) result: {res_copy}, Clipboard value: {clip_val!r}")

    # 3. Test EM_REPLACESEL (Enter)
    # Insert newline at the end (clear selection first by setting selection range to end)
    # First, get text length (WM_GETTEXTLENGTH is 0x000E)
    length = ctypes.windll.user32.SendMessageW(edit_hwnd, 0x000E, 0, 0)
    # Set selection to end to collapse it
    ctypes.windll.user32.SendMessageW(edit_hwnd, 0x00B1, length, length)
    # Insert newline + text
    ctypes.windll.user32.SendMessageW(edit_hwnd, 0x00C2, 1, "\r\nLine 3")
    print(f"[DEBUG] Text after inserting newline: {get_edit_content(hwnd)!r}")

    # 4. Test EM_UNDO
    # EM_UNDO is 0x00C7.
    res_undo = ctypes.windll.user32.SendMessageW(edit_hwnd, 0x00C7, 0, 0)
    print(f"[DEBUG] SendMessageW(EM_UNDO) result: {res_undo}")
    print(f"[DEBUG] Text after Undo: {get_edit_content(hwnd)!r}")

if __name__ == "__main__":
    run()
