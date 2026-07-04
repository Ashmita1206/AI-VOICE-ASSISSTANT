"""
Step Verifier
=============

Post-execution verification layer for the stateful execution engine.

After every tool handler returns, the executor calls :func:`dispatch_verify` to
check that the intended outcome was actually achieved on the system.  Verification
is best-effort: for some tools (e.g. ``press_key``) there is no observable side-
effect to check, so verification always returns True.  For application launches and
window-focus operations, concrete checks against the running process list and
foreground window state are performed.

The verifier **does not** block or retry — it simply inspects the current system
state and reports a pass/fail verdict.  Recovery and retry logic lives in
:mod:`execution.recovery`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

@dataclass
class VerifyResult:
    """Outcome of a post-execution verification check.

    Attributes
    ----------
    passed:
        True if the step's intended effect was confirmed.
    message:
        Human-readable explanation (for logs and UI feedback).
    """
    passed: bool
    message: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _try_psutil():
    try:
        import psutil
        return psutil
    except ImportError:
        return None


def _try_win32():
    try:
        import win32gui
        import win32process
        return win32gui, win32process
    except ImportError:
        return None, None


def _is_process_running(name: str) -> bool:
    """Return True if any process name contains *name* (case-insensitive)."""
    psutil = _try_psutil()
    if psutil is None:
        return True  # can't verify — assume ok
    name = name.lower().strip()
    try:
        for proc in psutil.process_iter(attrs=["name"]):
            p = (proc.info.get("name") or "").lower()
            p_clean = p[:-4] if p.endswith(".exe") else p
            if name in p_clean or p_clean in name:
                return True
    except Exception:
        pass
    return False


def _is_window_visible(fragment: str) -> bool:
    """Return True if a visible window title contains *fragment*."""
    win32gui, _ = _try_win32()
    if win32gui is None:
        return True  # can't verify — assume ok
    fragment = fragment.lower().strip()
    found = []
    try:
        def _cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).lower()
                if fragment in title:
                    found.append(True)
            return True
        win32gui.EnumWindows(_cb, None)
    except Exception:
        pass
    return bool(found)


def _is_window_foreground(fragment: str) -> bool:
    """Return True if the foreground window title contains *fragment*."""
    win32gui, _ = _try_win32()
    if win32gui is None:
        return True
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            title = win32gui.GetWindowText(hwnd).lower()
            return fragment.lower() in title
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Individual verifiers
# ---------------------------------------------------------------------------

def verify_application_launched(app_name: str) -> VerifyResult:
    """Verify that an application is running **and** has a visible window.

    Parameters
    ----------
    app_name:
        Canonical name of the application (e.g. ``"spotify"``).

    Returns
    -------
    VerifyResult
    """
    name = app_name.lower().strip()

    if not _is_process_running(name):
        return VerifyResult(
            passed=False,
            message=f"Verification failed: no running process found for '{app_name}'."
        )

    if not _is_window_visible(name):
        # Process is running but window hasn't appeared yet — partial pass
        # (common in first 1-2 seconds after launch).
        logger.debug(f"[VERIFY] Process '{app_name}' running but window not yet visible.")
        return VerifyResult(
            passed=True,
            message=(
                f"Process '{app_name}' is running (window not yet visible — "
                "may need wait_until_window_exists)."
            )
        )

    return VerifyResult(
        passed=True,
        message=f"Application '{app_name}' is running with a visible window."
    )


def verify_window_focused(target: str) -> VerifyResult:
    """Verify that the foreground window title matches *target*.

    Parameters
    ----------
    target:
        Window title fragment to look for.

    Returns
    -------
    VerifyResult
    """
    if _is_window_foreground(target):
        return VerifyResult(
            passed=True,
            message=f"Window '{target}' is the active foreground window."
        )
    # Window may exist but not be foreground — still viable if visible
    if _is_window_visible(target):
        return VerifyResult(
            passed=True,
            message=f"Window '{target}' is visible (not foreground, but usable)."
        )
    return VerifyResult(
        passed=False,
        message=f"Window matching '{target}' is not visible or foreground."
    )


def verify_text_typed(text: str) -> VerifyResult:
    """Best-effort verification that *text* was typed.

    Since pyautogui ``write()`` is fire-and-forget, we cannot reliably inspect the
    target input field's current value from outside the application.  This verifier
    returns True if the tool call did not raise an exception (which is already
    captured in the ExecutionResult). Clipboard comparison could be added in future.

    Parameters
    ----------
    text:
        The text that was typed.

    Returns
    -------
    VerifyResult
    """
    return VerifyResult(
        passed=True,
        message=f"Text typed ('{text[:30]}{'...' if len(text) > 30 else ''}'); "
                "input field state not inspectable externally."
    )


def verify_key_pressed(key: str) -> VerifyResult:
    """Verification for key press actions — always passes (fire-and-forget).

    Parameters
    ----------
    key:
        The key that was pressed.

    Returns
    -------
    VerifyResult
    """
    return VerifyResult(
        passed=True,
        message=f"Key '{key}' pressed (keystroke is fire-and-forget)."
    )


def verify_search_results_loaded(app_name: str, query: str) -> VerifyResult:
    """Heuristic check that search results appeared after a search action.

    Currently relies on checking that the application window is still visible and
    active (meaning it did not crash or close) after the search was submitted.
    A more precise implementation could use accessibility APIs or OCR.

    Parameters
    ----------
    app_name:
        Application in which search was performed.
    query:
        The search query submitted.

    Returns
    -------
    VerifyResult
    """
    if _is_window_visible(app_name):
        return VerifyResult(
            passed=True,
            message=f"Search for '{query}' submitted in '{app_name}' (window still active)."
        )
    return VerifyResult(
        passed=False,
        message=(
            f"'{app_name}' window disappeared after search for '{query}' — "
            "possible crash or unexpected close."
        )
    )


def verify_generic(tool: str, result_success: bool) -> VerifyResult:
    """Fallback verifier: trust the handler's own success flag.

    Parameters
    ----------
    tool:
        Tool name, for logging.
    result_success:
        The ``success`` field from the tool's :class:`ExecutionResult`.

    Returns
    -------
    VerifyResult
    """
    if result_success:
        return VerifyResult(
            passed=True,
            message=f"Tool '{tool}' reported success."
        )
    return VerifyResult(
        passed=False,
        message=f"Tool '{tool}' reported failure."
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def dispatch_verify(tool: str, args: dict, result) -> VerifyResult:
    """Route a completed step to the appropriate verifier.

    Called by the stateful executor after every tool execution (and after
    the optional wait phase).

    Parameters
    ----------
    tool:
        The canonical tool name that was executed.
    args:
        The step's argument dictionary.
    result:
        The :class:`~execution.schemas.ExecutionResult` returned by the handler.

    Returns
    -------
    VerifyResult
    """
    # If the handler itself reported failure, skip deep verification —
    # we already know it failed and should go to recovery.
    if not result.success:
        return VerifyResult(
            passed=False,
            message=f"Handler reported failure for '{tool}': {result.message}"
        )

    app = (
        args.get("application")
        or args.get("app")
        or args.get("target")
        or ""
    ).lower().strip()

    # Application launch / open tools
    if tool in ("open_application", "launch_application", "resolve_and_open"):
        opened_in_browser = getattr(result, "metadata", {}).get("opened_in_browser", False)
        if opened_in_browser:
            if not _is_window_visible(app):
                return VerifyResult(passed=False, message=f"Browser tab for '{app}' is not visible.")
            return VerifyResult(passed=True, message=f"Browser fallback for '{app}' is visible.")
        return verify_application_launched(app) if app else verify_generic(tool, result.success)

    # Window focus tools
    if tool in ("focus_window", "wait_for_window"):
        target = (args.get("target") or app).lower()
        return verify_window_focused(target) if target else verify_generic(tool, result.success)

    # Text input
    if tool == "type_text":
        return verify_text_typed(args.get("text", ""))

    # Key presses
    if tool in ("press_key", "hotkey"):
        return verify_key_pressed(args.get("key") or str(args))

    # In-application search
    if tool == "search_inside_application":
        query = args.get("query", "")
        # Determine the active app from session state
        from automation.desktop import get_active_app_name
        active_app = get_active_app_name() or app
        return verify_search_results_loaded(active_app, query)

    # Default: trust the handler's own success flag
    return verify_generic(tool, result.success)
