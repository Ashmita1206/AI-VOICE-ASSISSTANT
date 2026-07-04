"""
Wait Utilities
==============

Intelligent, condition-based wait primitives for the stateful execution engine.

Instead of blind ``time.sleep(N)`` calls, every wait polls an observable condition
(process existence, window title, foreground state, UI element presence) and returns
as soon as the condition is satisfied — or after a configurable timeout.

Each public function returns a :class:`WaitResult` so the caller can act on failure
(trigger recovery, abort, log debug info) rather than blindly continue.

Usage example::

    result = wait_until_application_ready("spotify", timeout=20)
    if not result.success:
        # trigger recovery
        ...
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Any
from execution.schemas import ExecutionResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

@dataclass
class WaitResult:
    """Outcome of a wait operation.

    Attributes
    ----------
    success:
        True if the condition was met within the timeout window.
    elapsed_ms:
        Wall-clock time spent waiting, in milliseconds.
    message:
        Human-readable description of outcome (for logging / UI feedback).
    """
    success: bool
    elapsed_ms: int = 0
    message: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _try_import_psutil():
    """Lazy import of psutil; returns None if unavailable."""
    try:
        import psutil
        return psutil
    except ImportError:
        return None


def _try_import_win32():
    """Lazy import of win32gui / win32process; returns (None, None) if unavailable."""
    try:
        import win32gui
        import win32process
        return win32gui, win32process
    except ImportError:
        return None, None


def _process_name_matches(proc_info: dict, name_fragment: str) -> bool:
    """Return True if a process name matches a fragment (case-insensitive)."""
    p_name = (proc_info.get("name") or "").lower()
    # Strip .exe suffix for cleaner comparison
    p_clean = p_name[:-4] if p_name.endswith(".exe") else p_name
    frag = name_fragment.lower().strip()
    return frag in p_clean or p_clean in frag


def _window_title_matches(hwnd, fragment: str, win32gui) -> bool:
    """Return True if a window handle has a title containing *fragment*."""
    if not win32gui.IsWindowVisible(hwnd):
        return False
    title = win32gui.GetWindowText(hwnd).lower()
    return fragment.lower() in title


# ---------------------------------------------------------------------------
# Public wait primitives
# ---------------------------------------------------------------------------

def wait_until_process_running(
    name: str,
    timeout: float = 15.0,
    poll_interval: float = 0.5,
) -> WaitResult:
    """Poll until a process whose name contains *name* appears in the process list.

    Parameters
    ----------
    name:
        Fragment of the process name to search for (e.g. ``"spotify"``).
    timeout:
        Maximum seconds to wait before giving up.
    poll_interval:
        Seconds between successive polls.

    Returns
    -------
    WaitResult
        ``.success`` is True when the process is found.
    """
    psutil = _try_import_psutil()
    if psutil is None:
        return WaitResult(
            success=False,
            message="psutil not available; cannot poll for process."
        )

    start = time.perf_counter()
    while True:
        elapsed = time.perf_counter() - start
        try:
            for proc in psutil.process_iter(attrs=["pid", "name"]):
                if _process_name_matches(proc.info, name):
                    ms = int(elapsed * 1000)
                    logger.debug(f"[WAIT] Process '{name}' found after {ms} ms.")
                    return WaitResult(
                        success=True,
                        elapsed_ms=ms,
                        message=f"Process '{name}' is running."
                    )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except Exception as exc:
            logger.debug(f"[WAIT] process poll error: {exc}")

        if elapsed >= timeout:
            ms = int(elapsed * 1000)
            logger.debug(f"[WAIT] Timeout waiting for process '{name}' ({ms} ms).")
            return WaitResult(
                success=False,
                elapsed_ms=ms,
                message=f"Timeout ({timeout}s): process '{name}' did not appear."
            )
        time.sleep(poll_interval)


def wait_until_window_exists(
    title_fragment: str,
    timeout: float = 15.0,
    poll_interval: float = 0.5,
) -> WaitResult:
    """Poll until a visible window whose title contains *title_fragment* appears.

    Parameters
    ----------
    title_fragment:
        Substring to search for in window titles (case-insensitive).
    timeout:
        Maximum seconds to wait.
    poll_interval:
        Seconds between polls.

    Returns
    -------
    WaitResult
    """
    win32gui, _ = _try_import_win32()

    start = time.perf_counter()
    while True:
        elapsed = time.perf_counter() - start

        if win32gui is None:
            # Fallback: consider condition met if we can't enumerate windows
            return WaitResult(
                success=True,
                elapsed_ms=int(elapsed * 1000),
                message="win32gui unavailable; assuming window exists."
            )

        found = []
        try:
            def _enum_cb(hwnd, _extra):
                if _window_title_matches(hwnd, title_fragment, win32gui):
                    found.append(hwnd)
                return True
            win32gui.EnumWindows(_enum_cb, None)
        except Exception as exc:
            logger.debug(f"[WAIT] EnumWindows error: {exc}")

        if found:
            ms = int(elapsed * 1000)
            logger.debug(f"[WAIT] Window '{title_fragment}' found after {ms} ms.")
            return WaitResult(
                success=True,
                elapsed_ms=ms,
                message=f"Window matching '{title_fragment}' appeared."
            )

        if elapsed >= timeout:
            ms = int(elapsed * 1000)
            return WaitResult(
                success=False,
                elapsed_ms=ms,
                message=f"Timeout ({timeout}s): window '{title_fragment}' did not appear."
            )
        time.sleep(poll_interval)


def wait_until_window_active(
    title_fragment: str,
    timeout: float = 10.0,
    poll_interval: float = 0.4,
) -> WaitResult:
    """Poll until the foreground window title contains *title_fragment*.

    Parameters
    ----------
    title_fragment:
        Fragment expected in the active window title.
    timeout:
        Maximum seconds to wait.
    poll_interval:
        Seconds between polls.

    Returns
    -------
    WaitResult
    """
    win32gui, _ = _try_import_win32()

    start = time.perf_counter()
    while True:
        elapsed = time.perf_counter() - start

        if win32gui is None:
            return WaitResult(
                success=True,
                elapsed_ms=int(elapsed * 1000),
                message="win32gui unavailable; assuming window is active."
            )

        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                title = win32gui.GetWindowText(hwnd).lower()
                if title_fragment.lower() in title:
                    ms = int(elapsed * 1000)
                    logger.debug(f"[WAIT] Window '{title_fragment}' is active after {ms} ms.")
                    return WaitResult(
                        success=True,
                        elapsed_ms=ms,
                        message=f"Window '{title_fragment}' is now the active foreground window."
                    )
        except Exception as exc:
            logger.debug(f"[WAIT] GetForegroundWindow error: {exc}")

        if elapsed >= timeout:
            ms = int(elapsed * 1000)
            return WaitResult(
                success=False,
                elapsed_ms=ms,
                message=f"Timeout ({timeout}s): window '{title_fragment}' did not become active."
            )
        time.sleep(poll_interval)


def wait_until_application_ready(
    app_name: str,
    timeout: float = 20.0,
    poll_interval: float = 0.5,
    skip_process_check: bool = False,
) -> WaitResult:
    """Composite wait: process running **and** window visible **and** window active.

    This is the primary wait primitive used after launching an application.
    Each phase has its own sub-timeout derived from *timeout*.

    Parameters
    ----------
    app_name:
        Canonical name of the application (e.g. ``"spotify"``).
    timeout:
        Total maximum seconds allowed across all phases.
    poll_interval:
        Polling interval forwarded to each sub-wait.

    Returns
    -------
    WaitResult
        Reports the first phase that failed, or success if all passed.
    """
    start = time.perf_counter()

    # Phase 1: Process must appear (if not skipped)
    if not skip_process_check:
        phase_timeout = timeout * 0.5  # first half of budget
        r1 = wait_until_process_running(app_name, timeout=phase_timeout, poll_interval=poll_interval)
        if not r1.success:
            return WaitResult(
                success=False,
                elapsed_ms=int((time.perf_counter() - start) * 1000),
                message=f"Application '{app_name}' process did not start: {r1.message}"
            )

        remaining = timeout - (time.perf_counter() - start)
        if remaining <= 0:
            return WaitResult(success=False, elapsed_ms=int(timeout * 1000),
                              message=f"Timeout after process wait for '{app_name}'.")
    else:
        remaining = timeout

    # Phase 2: Window must appear
    phase_timeout2 = remaining * 0.6
    r2 = wait_until_window_exists(app_name, timeout=phase_timeout2, poll_interval=poll_interval)
    if not r2.success:
        return WaitResult(
            success=False,
            elapsed_ms=int((time.perf_counter() - start) * 1000),
            message=f"Application '{app_name}' window did not appear: {r2.message}"
        )

    remaining = timeout - (time.perf_counter() - start)
    if remaining <= 0:
        return WaitResult(success=False, elapsed_ms=int(timeout * 1000),
                          message=f"Timeout after window wait for '{app_name}'.")

    # Phase 3: Window must become active
    r3 = wait_until_window_active(app_name, timeout=remaining, poll_interval=poll_interval)
    total_ms = int((time.perf_counter() - start) * 1000)

    if not r3.success:
        logger.warning(
            f"[WAIT] '{app_name}' window exists but did not become active within timeout."
        )
        return WaitResult(
            success=False,
            elapsed_ms=total_ms,
            message=(
                f"Application '{app_name}' window exists but did not become active "
                f"within {timeout}s timeout."
            )
        )

    return WaitResult(
        success=True,
        elapsed_ms=total_ms,
        message=f"Application '{app_name}' is fully ready (process + window + active)."
    )


def wait_until_element_ready(
    label: str,
    timeout: float = 10.0,
    poll_interval: float = 0.5,
) -> WaitResult:
    """Poll until a UI element with *label* can be located on screen.

    Uses :func:`automation.desktop.locate_ui_element` internally.

    Parameters
    ----------
    label:
        Human-readable label of the UI element (e.g. ``"search"``).
    timeout:
        Maximum seconds to wait.
    poll_interval:
        Seconds between polls.

    Returns
    -------
    WaitResult
    """
    start = time.perf_counter()
    while True:
        elapsed = time.perf_counter() - start
        try:
            from automation.desktop import locate_ui_element
            res = locate_ui_element({"element_type": "input", "label": label})
            if res.success:
                ms = int(elapsed * 1000)
                logger.debug(f"[WAIT] Element '{label}' ready after {ms} ms.")
                return WaitResult(
                    success=True,
                    elapsed_ms=ms,
                    message=f"UI element '{label}' is ready."
                )
        except Exception as exc:
            logger.debug(f"[WAIT] element_ready poll error: {exc}")

        if elapsed >= timeout:
            ms = int(elapsed * 1000)
            return WaitResult(
                success=False,
                elapsed_ms=ms,
                message=f"Timeout ({timeout}s): UI element '{label}' not ready."
            )
        time.sleep(poll_interval)


def wait_until_browser_loaded(
    timeout: float = 15.0,
    poll_interval: float = 0.6,
) -> WaitResult:
    """Wait until the browser foreground window title stabilises (stops changing).

    Uses the heuristic that a browser loading a page frequently changes its title;
    once the title stops changing between two polls, the page is considered loaded.

    Parameters
    ----------
    timeout:
        Maximum seconds to wait.
    poll_interval:
        Seconds between title samples.

    Returns
    -------
    WaitResult
    """
    win32gui, _ = _try_import_win32()

    start = time.perf_counter()
    prev_title: Optional[str] = None

    while True:
        elapsed = time.perf_counter() - start

        current_title: Optional[str] = None
        if win32gui:
            try:
                hwnd = win32gui.GetForegroundWindow()
                if hwnd:
                    current_title = win32gui.GetWindowText(hwnd).lower()
            except Exception:
                pass

        if current_title and current_title == prev_title and current_title not in ("", "loading..."):
            ms = int(elapsed * 1000)
            logger.debug(f"[WAIT] Browser title stabilised: '{current_title}' after {ms} ms.")
            return WaitResult(
                success=True,
                elapsed_ms=ms,
                message=f"Browser page loaded (stable title: '{current_title}')."
            )

        prev_title = current_title

        if elapsed >= timeout:
            ms = int(elapsed * 1000)
            return WaitResult(
                success=False,
                elapsed_ms=ms,
                message=f"Timeout ({timeout}s): browser page did not finish loading."
            )
        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Dispatcher (used by executor to resolve "wait_for" metadata field)
# ---------------------------------------------------------------------------

def dispatch_wait(
    wait_for: str,
    args: dict,
    result: Optional[ExecutionResult] = None,
    timeout: Optional[float] = None,
) -> WaitResult:
    """Route a ``wait_for`` metadata string to the appropriate wait primitive.

    Called by the stateful executor when a step carries a ``wait_for`` field.

    Parameters
    ----------
    wait_for:
        One of: ``"window_ready"``, ``"process_running"``, ``"window_exists"``,
        ``"window_active"``, ``"element_ready"``, ``"browser_loaded"``.
    args:
        The step's args dict (used to extract ``application``, ``query``, etc.).
    timeout:
        Override timeout in seconds; falls back to per-function defaults if None.

    Returns
    -------
    WaitResult
    """
    # Resolve the target name from common arg keys
    app_name = (
        args.get("application")
        or args.get("app")
        or args.get("target")
        or args.get("query")
        or ""
    ).lower().strip()

    kwargs: dict = {}
    if timeout is not None:
        kwargs["timeout"] = float(timeout)
        
    opened_in_browser = False
    reused_window = False
    if result:
        meta = getattr(result, "metadata", {}) or {}
        opened_in_browser = meta.get("opened_in_browser", False)
        reused_window = meta.get("reused_window", False)

    wf = wait_for.lower().strip()

    if wf in ("window_ready", "application_ready"):
        if opened_in_browser or reused_window:
            return wait_until_application_ready(app_name, skip_process_check=True, **kwargs)
        return wait_until_application_ready(app_name, skip_process_check=False, **kwargs)
    elif wf == "process_running":
        return wait_until_process_running(app_name, **kwargs)
    elif wf == "window_exists":
        return wait_until_window_exists(app_name, **kwargs)
    elif wf == "window_active":
        return wait_until_window_active(app_name, **kwargs)
    elif wf == "element_ready":
        label = args.get("query") or args.get("label") or app_name
        return wait_until_element_ready(label, **kwargs)
    elif wf == "browser_loaded":
        return wait_until_browser_loaded(**kwargs)
    else:
        logger.warning(f"[WAIT] Unknown wait_for value '{wait_for}'; skipping wait.")
        return WaitResult(
            success=True,
            message=f"Unknown wait_for '{wait_for}' — wait skipped."
        )
