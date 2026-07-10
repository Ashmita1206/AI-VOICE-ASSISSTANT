"""
notepad_diagnostic.py
======================
Live end-to-end diagnostic for Notepad automation.
Run this directly: python notepad_diagnostic.py

Does NOT use pytest. Every result is printed to the console.
Produces a full log of window structure, focus state, and typing verification.
"""
import ctypes
import subprocess
import sys
import time

# ── dependency checks ─────────────────────────────────────────────────────────
try:
    import win32gui, win32process, win32con, win32api
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    print("[DIAG] WARN: pywin32 not available — limited detection")

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("[DIAG] WARN: psutil not available")

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False
    print("[DIAG] WARN: pyautogui not available")

try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False
    print("[DIAG] WARN: pyperclip not available")

SEP = "=" * 72


# ─────────────────────────────────────────────────────────────────────────────
# Helper: enumerate ALL top-level windows
# ─────────────────────────────────────────────────────────────────────────────

def enum_all_windows(label=""):
    """Print every visible top-level window with hwnd/class/title/pid."""
    if not HAS_WIN32:
        return []
    results = []
    fg = win32gui.GetForegroundWindow()

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return True
        cls = win32gui.GetClassName(hwnd)
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            pid = -1
        minimized = win32gui.IsIconic(hwnd)
        is_fg = (hwnd == fg)
        results.append(dict(hwnd=hwnd, cls=cls, title=title,
                            pid=pid, minimized=minimized, fg=is_fg))
        return True

    win32gui.EnumWindows(_cb, None)
    tag = f" [{label}]" if label else ""
    print(f"\n[DIAG] All visible top-level windows{tag}:")
    for r in results:
        fg_mark = " ◄ FOREGROUND" if r["fg"] else ""
        min_mark = " [minimized]" if r["minimized"] else ""
        print(f"  HWND={r['hwnd']:8d}  CLS={r['cls']!r:32s}  "
              f"PID={r['pid']:6d}  TITLE={r['title']!r}{fg_mark}{min_mark}")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Helper: enumerate child windows of a given hwnd
# ─────────────────────────────────────────────────────────────────────────────

def enum_children(hwnd, depth=0, max_depth=6):
    """Recursively print child windows."""
    if not HAS_WIN32 or depth > max_depth:
        return
    children = []

    def _cb(child_hwnd, _):
        children.append(child_hwnd)
        return True

    try:
        win32gui.EnumChildWindows(hwnd, _cb, None)
    except Exception:
        return

    for child in children:
        try:
            cls   = win32gui.GetClassName(child)
            title = win32gui.GetWindowText(child)
            vis   = win32gui.IsWindowVisible(child)
            try:
                rect  = win32gui.GetWindowRect(child)
                w = rect[2] - rect[0]
                h = rect[3] - rect[1]
                size  = f"{w}×{h}"
            except Exception:
                size = "?"
            indent = "  " * (depth + 1)
            print(f"{indent}child HWND={child:8d}  CLS={cls!r:32s}  "
                  f"vis={vis}  size={size}  TITLE={title!r}")
        except Exception as exc:
            print(f"{'  '*(depth+1)}child HWND={child} ERROR: {exc}")
        # Recurse
        enum_children(child, depth + 1, max_depth)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: find the best Notepad HWND (title scan)
# ─────────────────────────────────────────────────────────────────────────────

def find_notepad_hwnd_title():
    """Find a Notepad window by title fragment."""
    if not HAS_WIN32:
        return None
    found = []

    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).lower()
            if "notepad" in title:
                found.append(hwnd)
        return True

    win32gui.EnumWindows(_cb, None)
    return found[0] if found else None


# ─────────────────────────────────────────────────────────────────────────────
# Helper: find the best Notepad HWND (psutil PID scan)
# ─────────────────────────────────────────────────────────────────────────────

def notepad_pids():
    if not HAS_PSUTIL:
        return []
    pids = []
    for proc in psutil.process_iter(attrs=["pid", "name"]):
        name = (proc.info.get("name") or "").lower()
        name = name[:-4] if name.endswith(".exe") else name
        if name == "notepad":
            pids.append(proc.info["pid"])
    return pids


def find_notepad_hwnd_pid():
    """Find Notepad windows by PID membership."""
    if not HAS_WIN32 or not HAS_PSUTIL:
        return None
    pids = set(notepad_pids())
    if not pids:
        return None
    found = []

    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                title = win32gui.GetWindowText(hwnd)
                if pid in pids and title:
                    found.append(hwnd)
            except Exception:
                pass
        return True

    win32gui.EnumWindows(_cb, None)
    return found[0] if found else None


# ─────────────────────────────────────────────────────────────────────────────
# Helper: force foreground
# ─────────────────────────────────────────────────────────────────────────────

def force_focus(hwnd):
    """Bring hwnd to foreground using Alt-key trick."""
    if not HAS_WIN32:
        return False
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, 9)
        else:
            win32gui.ShowWindow(hwnd, 5)
        win32gui.BringWindowToTop(hwnd)

        fg = win32gui.GetForegroundWindow()
        if fg == hwnd:
            return True

        try:
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        except Exception:
            pass

        try:
            win32gui.SetForegroundWindow(hwnd)
            if win32gui.GetForegroundWindow() == hwnd:
                return True
        except Exception:
            pass

        cur_tid = win32api.GetCurrentThreadId()
        fg_hwnd = win32gui.GetForegroundWindow()
        tgt_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
        fg_tid,  _ = win32process.GetWindowThreadProcessId(fg_hwnd) if fg_hwnd else (0, 0)

        attached = False
        if fg_tid and fg_tid != cur_tid:
            try:
                win32process.AttachThreadInput(cur_tid, fg_tid, True)
                attached = True
            except Exception:
                pass

        try:
            win32gui.SetForegroundWindow(hwnd)
            ctypes.windll.user32.SetActiveWindow(hwnd)
            ctypes.windll.user32.SetFocus(hwnd)
        except Exception:
            pass

        if attached:
            try:
                win32process.AttachThreadInput(cur_tid, fg_tid, False)
            except Exception:
                pass

        time.sleep(0.25)
        return win32gui.GetForegroundWindow() == hwnd
    except Exception as exc:
        print(f"[DIAG] force_focus error: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Helper: kill all Notepad instances
# ─────────────────────────────────────────────────────────────────────────────

def kill_notepad():
    subprocess.run(["taskkill", "/f", "/im", "notepad.exe"],
                   capture_output=True)
    time.sleep(0.8)
    print("[DIAG] Killed any existing Notepad instances.")


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 — Window structure discovery
# ─────────────────────────────────────────────────────────────────────────────

def phase1_structure():
    print(f"\n{SEP}")
    print("PHASE 1 — Notepad window structure discovery")
    print(SEP)

    kill_notepad()

    print("\n[DIAG] Launching notepad.exe …")
    proc = subprocess.Popen(["notepad.exe"])
    print(f"[DIAG] subprocess.Popen returned PID={proc.pid}")

    # Poll for window
    print("[DIAG] Polling for a window with 'notepad' in title …")
    hwnd = None
    for i in range(40):
        time.sleep(0.3)
        hwnd = find_notepad_hwnd_title()
        if hwnd:
            break

    if hwnd is None:
        print("[DIAG] ERROR: No Notepad window found after 12 s!")
        print("[DIAG] Trying PID-based scan …")
        hwnd = find_notepad_hwnd_pid()

    if hwnd is None:
        print("[DIAG] FATAL: Cannot find Notepad window at all. Aborting phase 1.")
        return None

    title = win32gui.GetWindowText(hwnd)
    cls   = win32gui.GetClassName(hwnd)
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:
        pid = -1

    print(f"\n[DIAG] Found Notepad:")
    print(f"  HWND  = {hwnd}")
    print(f"  Class = {cls!r}")
    print(f"  Title = {title!r}")
    print(f"  PID   = {pid}")
    print(f"  notepad.exe PIDs (psutil) = {notepad_pids()}")

    # Check title-scan vs pid-scan consistency
    hwnd_title = find_notepad_hwnd_title()
    hwnd_pid   = find_notepad_hwnd_pid()
    print(f"\n[DIAG] Scan consistency:")
    print(f"  find_notepad_hwnd_title() = {hwnd_title}")
    print(f"  find_notepad_hwnd_pid()   = {hwnd_pid}")

    print(f"\n[DIAG] Child window tree of HWND={hwnd}:")
    enum_children(hwnd)

    enum_all_windows("after first launch")
    return hwnd


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2 — Duplicate-open test
# ─────────────────────────────────────────────────────────────────────────────

def phase2_duplicate_open(hwnd_first):
    print(f"\n{SEP}")
    print("PHASE 2 — Duplicate open test")
    print(SEP)

    pids_before = notepad_pids()
    title_hwnd_before = find_notepad_hwnd_title()
    pid_hwnd_before   = find_notepad_hwnd_pid()

    print(f"[DIAG] Before 2nd open_notepad call:")
    print(f"  notepad PIDs         = {pids_before}")
    print(f"  title-based HWND     = {title_hwnd_before}")
    print(f"  pid-based HWND       = {pid_hwnd_before}")
    print(f"  original HWND        = {hwnd_first}")

    # Simulate what the controller does
    print("\n[DIAG] Simulating open_notepad() step 1: process check …")
    pids = notepad_pids()
    print(f"  _notepad_pids() = {pids}")

    if pids:
        print("  Process running — looking for window …")
        hwnd_found = find_notepad_hwnd_title()
        print(f"  find_notepad_hwnd_title() = {hwnd_found}")
        if hwnd_found:
            title = win32gui.GetWindowText(hwnd_found)
            cls   = win32gui.GetClassName(hwnd_found)
            print(f"  --> Would reuse HWND={hwnd_found} class={cls!r} title={title!r}")
            print("  ✓ CORRECT: would NOT spawn a new instance")
        else:
            print("  ✗ WRONG: window not found — would spawn new instance!")
    else:
        print("  Process NOT found — would spawn new instance!")

    # Now actually call subprocess.Popen and record what happens
    print("\n[DIAG] Calling subprocess.Popen(['notepad.exe']) a 2nd time …")
    proc2 = subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)

    pids_after = notepad_pids()
    all_wins_after = enum_all_windows("after 2nd Popen")
    notepad_wins = [w for w in all_wins_after if "notepad" in w["title"].lower()]
    print(f"\n[DIAG] Notepad windows after 2nd Popen:")
    for w in notepad_wins:
        print(f"  HWND={w['hwnd']}  PID={w['pid']}  TITLE={w['title']!r}  CLS={w['cls']!r}")
    print(f"  notepad PIDs now = {pids_after}")

    if len(notepad_wins) > 1:
        print("  ✗ CONFIRMED: 2nd Popen DID open a second window")
    elif len(notepad_wins) == 1:
        print("  ✓ OK: 2nd Popen was absorbed (single-instance behaviour)")
    else:
        print("  ? No Notepad windows found")


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3 — Focus and typing test
# ─────────────────────────────────────────────────────────────────────────────

def phase3_typing(hwnd):
    print(f"\n{SEP}")
    print("PHASE 3 — Focus and typing test")
    print(SEP)

    if not HAS_PYAUTOGUI:
        print("[DIAG] pyautogui not available — cannot test typing")
        return

    pyautogui.FAILSAFE = False

    # ── Step A: Focus ────────────────────────────────────────────────────────
    print(f"\n[DIAG] Attempting to focus HWND={hwnd} …")
    fg_before = win32gui.GetForegroundWindow()
    fg_before_title = win32gui.GetWindowText(fg_before)
    print(f"  Foreground BEFORE: HWND={fg_before} title={fg_before_title!r}")

    ok = force_focus(hwnd)
    time.sleep(0.3)

    fg_after = win32gui.GetForegroundWindow()
    fg_after_title = win32gui.GetWindowText(fg_after)
    print(f"  force_focus() returned: {ok}")
    print(f"  Foreground AFTER:  HWND={fg_after} title={fg_after_title!r}")
    print(f"  Is Notepad foreground? {fg_after == hwnd}")

    # ── Step B: Find edit control ─────────────────────────────────────────────
    print(f"\n[DIAG] Enumerating child controls of HWND={hwnd} to find editor …")
    edit_candidates = []
    all_children = []

    def _collect_children(parent_hwnd, depth=0):
        def _cb(child_hwnd, _):
            all_children.append((child_hwnd, depth))
            return True
        try:
            win32gui.EnumChildWindows(parent_hwnd, _cb, None)
        except Exception:
            pass

    _collect_children(hwnd)
    print(f"  Total child controls: {len(all_children)}")
    for child_hwnd, _ in all_children:
        try:
            cls   = win32gui.GetClassName(child_hwnd)
            title = win32gui.GetWindowText(child_hwnd)
            vis   = win32gui.IsWindowVisible(child_hwnd)
            try:
                rect = win32gui.GetWindowRect(child_hwnd)
                w = rect[2] - rect[0]
                h = rect[3] - rect[1]
                sz = f"{w}×{h}"
            except Exception:
                sz = "?"
            print(f"    HWND={child_hwnd:8d}  CLS={cls!r:40s}  vis={vis}  sz={sz}  title={title!r}")
            if "edit" in cls.lower() or "rich" in cls.lower() or "text" in cls.lower():
                edit_candidates.append((child_hwnd, cls))
        except Exception:
            pass

    print(f"\n  Edit/Rich/Text candidates: {edit_candidates}")

    # ── Step C: UI Automation attempt ────────────────────────────────────────
    print("\n[DIAG] Trying UI Automation to find the editable region …")
    uia_edit_info = None
    try:
        import comtypes.client
        comtypes.client.GetModule("UIAutomationCore.dll")
        import comtypes.gen.UIAutomationClient as UIA

        pUIAutomation = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}",
            interface=UIA.IUIAutomation
        )
        root_elem = pUIAutomation.ElementFromHandle(hwnd)
        condition = pUIAutomation.CreatePropertyCondition(
            UIA.UIA_ControlTypePropertyId,
            UIA.UIA_EditControlTypeId
        )
        edit_elem = root_elem.FindFirst(UIA.TreeScope_Descendants, condition)
        if edit_elem:
            name     = edit_elem.CurrentName
            cls_name = edit_elem.CurrentClassName
            try:
                rect  = edit_elem.CurrentBoundingRectangle
                uia_rect = (rect.left, rect.top, rect.right, rect.bottom)
            except Exception:
                uia_rect = None
            print(f"  UIA found Edit control: name={name!r} cls={cls_name!r} rect={uia_rect}")
            uia_edit_info = dict(elem=edit_elem, rect=uia_rect, cls=cls_name)
        else:
            print("  UIA: no Edit control found via UIA_EditControlTypeId")

            # Try Document control type (used by some rich text editors)
            cond_doc = pUIAutomation.CreatePropertyCondition(
                UIA.UIA_ControlTypePropertyId,
                UIA.UIA_DocumentControlTypeId
            )
            doc_elem = root_elem.FindFirst(UIA.TreeScope_Descendants, cond_doc)
            if doc_elem:
                name     = doc_elem.CurrentName
                cls_name = doc_elem.CurrentClassName
                print(f"  UIA found Document control: name={name!r} cls={cls_name!r}")
                uia_edit_info = dict(elem=doc_elem, rect=None, cls=cls_name)
            else:
                print("  UIA: no Document control found either")

    except Exception as exc:
        print(f"  UIA attempt failed: {exc}")

    # ── Step D: Click in the editor ───────────────────────────────────────────
    print("\n[DIAG] Determining click target …")
    click_x, click_y = None, None

    if uia_edit_info and uia_edit_info.get("rect"):
        r = uia_edit_info["rect"]
        click_x = (r[0] + r[2]) // 2
        click_y = (r[1] + r[3]) // 2
        print(f"  Using UIA edit control rect → click at ({click_x}, {click_y})")
    elif edit_candidates:
        child_hwnd, cls = edit_candidates[0]
        try:
            rect = win32gui.GetWindowRect(child_hwnd)
            click_x = (rect[0] + rect[2]) // 2
            click_y = (rect[1] + rect[3]) // 2
            print(f"  Using Win32 edit control HWND={child_hwnd} cls={cls!r} → click at ({click_x}, {click_y})")
        except Exception as exc:
            print(f"  Cannot get rect for Win32 edit: {exc}")
    else:
        # Fall back to Notepad frame centre
        try:
            rect = win32gui.GetWindowRect(hwnd)
            click_x = (rect[0] + rect[2]) // 2
            click_y = (rect[1] + rect[3]) // 2
            print(f"  No edit child found — clicking Notepad frame centre ({click_x}, {click_y})")
        except Exception as exc:
            print(f"  Cannot get frame rect: {exc}")

    if click_x is not None:
        pyautogui.FAILSAFE = False
        print(f"\n[DIAG] Clicking at ({click_x}, {click_y}) …")
        pyautogui.click(click_x, click_y)
        time.sleep(0.4)
        fg_after_click = win32gui.GetForegroundWindow()
        print(f"  Foreground after click: HWND={fg_after_click} title={win32gui.GetWindowText(fg_after_click)!r}")
        print(f"  Is Notepad foreground? {fg_after_click == hwnd}")

    # ── Step E: Paste text via clipboard ─────────────────────────────────────
    SENTINEL = "DIAG_UNIQUE_7x3q9z"
    print(f"\n[DIAG] Typing sentinel text via clipboard: {SENTINEL!r} …")

    if HAS_PYPERCLIP:
        pyperclip.copy(SENTINEL)
        time.sleep(0.1)
        clip_check = pyperclip.paste()
        print(f"  Clipboard content after copy: {clip_check!r}")

        pyautogui.FAILSAFE = False
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.5)
        print("  Ctrl+V sent")
    else:
        pyautogui.FAILSAFE = False
        pyautogui.write(SENTINEL, interval=0.05)
        time.sleep(0.5)
        print("  pyautogui.write() used (no pyperclip)")

    # ── Step F: Read back ─────────────────────────────────────────────────────
    print(f"\n[DIAG] Reading back content: Ctrl+A → Ctrl+C → clipboard …")
    pyautogui.FAILSAFE = False

    # Re-click to make sure focus is still in editor
    if click_x is not None:
        pyautogui.click(click_x, click_y)
        time.sleep(0.3)

    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "c")
    time.sleep(0.4)

    if HAS_PYPERCLIP:
        content = pyperclip.paste()
        print(f"  Clipboard after Ctrl+A+C: {content!r}")
        if SENTINEL in content:
            print(f"\n  ✓ SUCCESS: Sentinel found in clipboard — typing works!")
        else:
            print(f"\n  ✗ FAILURE: Sentinel NOT found in clipboard — typing broken!")
    else:
        print("  (Cannot verify — pyperclip not available)")

    # Deselect
    pyautogui.press("right")


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4 — Win32 SendMessage approach
# ─────────────────────────────────────────────────────────────────────────────

def phase4_sendmessage(hwnd):
    """Try typing via Win32 WM_SETTEXT / EM_SETSEL / WM_CHAR to the edit control."""
    print(f"\n{SEP}")
    print("PHASE 4 — Win32 SendMessage typing approach")
    print(SEP)

    if not HAS_WIN32:
        print("[DIAG] win32 not available")
        return

    # Find edit child
    edit_hwnd = None
    def _cb(child, _):
        nonlocal edit_hwnd
        try:
            cls = win32gui.GetClassName(child)
            if "edit" in cls.lower() and win32gui.IsWindowVisible(child):
                edit_hwnd = child
        except Exception:
            pass
        return True

    try:
        win32gui.EnumChildWindows(hwnd, _cb, None)
    except Exception:
        pass

    if edit_hwnd is None:
        print("[DIAG] No Edit class child found — SendMessage approach N/A")
        return

    SENTINEL2 = "DIAG_SENDMSG_abc"
    WM_SETTEXT = 0x000C
    print(f"[DIAG] Found Edit HWND={edit_hwnd}")
    print(f"[DIAG] Sending WM_SETTEXT with {SENTINEL2!r} …")

    try:
        import ctypes
        result = ctypes.windll.user32.SendMessageW(
            edit_hwnd, WM_SETTEXT, 0, SENTINEL2
        )
        print(f"  SendMessageW(WM_SETTEXT) returned: {result}")
        time.sleep(0.3)

        # Read it back with WM_GETTEXT
        buf = ctypes.create_unicode_buffer(512)
        n = ctypes.windll.user32.SendMessageW(edit_hwnd, 0x000D, 512, buf)
        content = buf.value
        print(f"  WM_GETTEXT returned {n} chars: {content!r}")
        if SENTINEL2 in content:
            print("  ✓ WM_SETTEXT worked — edit control is reachable by HWND")
        else:
            print("  ✗ WM_SETTEXT did not set text (UWP/XAML editor?)")
    except Exception as exc:
        print(f"  SendMessage approach failed: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(SEP)
    print("Notepad Automation Live Diagnostic")
    print(SEP)
    print(f"Python {sys.version}")
    print(f"Platform: {sys.platform}")

    if not HAS_WIN32:
        print("FATAL: pywin32 is required. Aborting.")
        sys.exit(1)

    hwnd = phase1_structure()
    if hwnd is None:
        print("Cannot continue without a Notepad HWND")
        sys.exit(1)

    phase2_duplicate_open(hwnd)

    # Kill extra windows, keep one
    kill_notepad()
    print("[DIAG] Relaunching single clean Notepad for typing test …")
    subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    hwnd = find_notepad_hwnd_title()
    if not hwnd:
        hwnd = find_notepad_hwnd_pid()
    if not hwnd:
        print("[DIAG] FATAL: Cannot find Notepad for typing test")
        sys.exit(1)
    print(f"[DIAG] Typing test will use HWND={hwnd} "
          f"cls={win32gui.GetClassName(hwnd)!r} "
          f"title={win32gui.GetWindowText(hwnd)!r}")

    phase3_typing(hwnd)
    phase4_sendmessage(hwnd)

    print(f"\n{SEP}")
    print("Diagnostic complete. See output above for findings.")
    print(SEP)
