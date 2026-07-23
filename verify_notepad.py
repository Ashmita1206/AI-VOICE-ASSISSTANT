"""
verify_notepad.py
=================
Manual validation script that uses the real automation module under test.
Run this directly: python verify_notepad.py
"""
import sys
import time
import pyperclip

# Ensure the workspace is in the path
sys.path.insert(0, r"d:\ai voice assisstant")

from automation.notepad import NotepadController, _controller

def run_test():
    print("=" * 80)
    print("STARTING REAL DESKTOP INTEGRATION TEST")
    print("=" * 80)

    # 1. Close any existing notepad first to have a clean state
    import subprocess
    subprocess.run(["taskkill", "/f", "/im", "notepad.exe"], capture_output=True)
    time.sleep(1.0)
    print("[TEST] Killed existing notepad processes.")

    # 2. Call open_notepad first time
    print("[TEST] Calling open_notepad (first time) ...")
    r1 = _controller.open_notepad()
    print(f"[TEST] Result 1: success={r1.success}, message='{r1.message}'")
    if not r1.success:
        print("[TEST] FATAL: First open failed")
        return False
    time.sleep(1.0)

    # Record running notepad PIDs
    import psutil
    pids_after_first = [p.pid for p in psutil.process_iter() if p.name().lower() == "notepad.exe"]
    print(f"[TEST] Running notepad PIDs: {pids_after_first}")

    # 3. Call open_notepad second time (should reuse window)
    print("[TEST] Calling open_notepad (second time) ...")
    r2 = _controller.open_notepad()
    print(f"[TEST] Result 2: success={r2.success}, message='{r2.message}'")
    if not r2.success:
        print("[TEST] FATAL: Second open failed")
        return False
    time.sleep(1.0)

    pids_after_second = [p.pid for p in psutil.process_iter() if p.name().lower() == "notepad.exe"]
    print(f"[TEST] Running notepad PIDs now: {pids_after_second}")

    if len(pids_after_second) > len(pids_after_first) or len(pids_after_second) > 1:
        print("[TEST] FAILURE: Duplicate notepad processes spawned!")
        return False
    print("[TEST] SUCCESS: No duplicate process spawned.")

    # 4. Type a unique string
    unique_str = "NOTEPAD_E2E_VERIFICATION_SUCCESS_12345"
    print("[TEST] Clearing any pre-existing text...")
    _controller.clear_document()
    time.sleep(0.5)
    print(f"[TEST] Typing unique string: '{unique_str}' ...")
    r3 = _controller.type_text(unique_str)
    print(f"[TEST] Result 3: success={r3.success}, message='{r3.message}'")
    if not r3.success:
        print("[TEST] FATAL: Typing failed")
        return False
    time.sleep(1.0)

    # 5. Read back text via Ctrl+A -> Ctrl+C
    print("[TEST] Reading back content from Notepad ...")
    # Clear clipboard first
    pyperclip.copy("")
    
    # Use select all and copy from controller
    r_select = _controller.select_all()
    print(f"[TEST] Select All: success={r_select.success}")
    time.sleep(0.3)
    
    r_copy = _controller.copy()
    print(f"[TEST] Copy: success={r_copy.success}")
    time.sleep(0.5)

    content = pyperclip.paste().strip()
    print(f"[TEST] Content read from clipboard: '{content}'")

    if content == unique_str:
        print("[TEST] SUCCESS: Content matches unique string exactly!")
        return True
    else:
        print(f"[TEST] FAILURE: Content '{content}' does not match expected '{unique_str}'")
        return False

if __name__ == "__main__":
    success = run_test()
    if success:
        print("\nALL DESKTOP INTEGRATION TESTS PASSED SUCCESSFULLY! ✅")
        sys.exit(0)
    else:
        print("\nDESKTOP INTEGRATION TESTS FAILED! ❌")
        sys.exit(1)
