"""
Execution Engine
================

Reads ActionSteps from an ExecutionPlan, runs them through the safety layer,
dispatches them to the registered handler, and returns a list of ExecutionResults.
"""

import logging
import shlex
from typing import Any, Callable, Optional

from agentic.schemas import ExecutionPlan, ActionStep
from execution.schemas import ExecutionResult
from execution.registry import get_handler, load_all_tools

logger = logging.getLogger(__name__)

# Load handlers
load_all_tools()

from agentic.permissions import PermissionManager

class DesktopExecutor:
    """Executes a parsed ExecutionPlan against the local system with advanced permissions."""

    def __init__(self):
        # We can store pending steps here if a confirmation is needed
        self.pending_steps: list[ActionStep] = []

    def execute(self, plan: ExecutionPlan, progress_callback: Optional[Callable[[str], None]] = None) -> list[dict[str, Any]]:
        """Run all steps sequentially. Stop and ask if confirmation needed."""
        results = []
        import time
        import os
        
        # Safely move cursor and disable fail-safe to prevent triggers in headless environments
        try:
            import pyautogui
            if pyautogui:
                pyautogui.FAILSAFE = False
        except Exception:
            pass
            
        try:
            import sys
            if sys.platform.startswith("win"):
                import ctypes
                # Move to safe middle screen coordinate (500, 500) natively
                ctypes.windll.user32.SetCursorPos(500, 500)
            else:
                import pyautogui
                if pyautogui:
                    x, y = pyautogui.position()
                    if x == 0 and y == 0:
                        pyautogui.moveTo(500, 500)
        except Exception:
            pass

        def _emit(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)

        for i, step in enumerate(plan.steps):
            _emit(f"Running tool: {step.tool}")
            res = self.execute_step(step, progress_callback=progress_callback)
            
            # If a step required confirmation, save the remaining plan steps to PendingActionManager
            if res.requires_confirmation:
                _emit(f"Requires confirmation: {res.message}")
                remaining_steps = plan.steps[i:]
                remaining_plan_dict = {
                    "intent": getattr(plan, "intent", "open_resource") if hasattr(plan, "intent") else "open_resource",
                    "steps": [{"tool": s.tool, "args": s.args} for s in remaining_steps]
                }
                
                from agentic.memory.pending_action import PendingActionManager
                confirmation_id = PendingActionManager.save(remaining_plan_dict)
                
                # Update execution result confirmation ID
                res.confirmation_id = confirmation_id
                
                # Synchronise session state pending action ID
                from agentic.memory.session_state import get_session
                session = get_session()
                if session.pending_action:
                    session.pending_action["id"] = confirmation_id
                
                results.append(res.to_dict())
                break
                
            # If a step failed, attempt automated recovery/replanning
            if not res.success:
                _emit(f"Step '{step.tool}' failed — attempting recovery...")
                print(f"[RECOVERY] Step '{step.tool}' failed. Attempting recovery replan...")
                try:
                    # 1. Take a screenshot (with safe try-except)
                    import pyautogui
                    os.makedirs("data", exist_ok=True)
                    screenshot_path = os.path.join("data", f"recovery_{int(time.time())}.png")
                    try:
                        pyautogui.screenshot(screenshot_path)
                        _emit("Recovery screenshot captured")
                        print(f"[RECOVERY] Screenshot captured at: {screenshot_path}")
                    except Exception as scr_err:
                        print(f"[RECOVERY] Screenshot skipped: {scr_err}")

                    # 2. Inspect active UI and active window
                    from automation.desktop import get_active_app_name, focus_window
                    active_app = get_active_app_name()
                    _emit(f"Active foreground app: {active_app}")
                    print(f"[RECOVERY] Active foreground app: '{active_app}'")

                    # 3. Focus target application or launch if focus failed
                    target_app = None
                    if step.tool == "search_inside_application":
                        from agentic.memory.session_state import get_session
                        target_app = get_session().last_application or "WhatsApp"
                    elif "app" in step.args:
                        target_app = step.args["app"]
                    elif "application" in step.args:
                        target_app = step.args["application"]
                    elif "target" in step.args:
                        target_app = step.args["target"]

                    if step.tool == "focus_window" and not res.success:
                        _emit(f"Focus failed — attempting to launch '{target_app}'...")
                        print(f"[RECOVERY] Focus failed. Attempting to launch application '{target_app}'...")
                        from automation.applications import launch_application
                        launch_res = launch_application({"application": target_app})
                        if launch_res.success:
                            time.sleep(2.0)
                            res = launch_res
                            _emit(f"Application '{target_app}' launched successfully")
                            print(f"[RECOVERY] Application launched successfully. Resuming plan.")
                        else:
                            _emit(f"Launch failed: {launch_res.message}")
                            print(f"[RECOVERY] Launch failed: {launch_res.message}")
                    elif target_app and active_app != target_app.lower():
                        _emit(f"Refocusing window: {target_app}")
                        print(f"[RECOVERY] Refocusing window: '{target_app}'")
                        focus_res = focus_window({"target": target_app})
                        if focus_res.success:
                            time.sleep(1.0)
                            _emit(f"Retrying '{step.tool}'...")
                            print(f"[RECOVERY] Retrying execution of '{step.tool}'...")
                            retry_res = self.execute_step(step, progress_callback=progress_callback)
                            if retry_res.success:
                                _emit(f"Retry succeeded")
                                print(f"[RECOVERY] Step succeeded on retry! Resuming plan execution.")
                                res = retry_res
                            else:
                                _emit(f"Retry failed: {retry_res.message}")
                                print(f"[RECOVERY] Retry failed: {retry_res.message}")
                        else:
                            _emit(f"Failed to focus '{target_app}': {focus_res.message}")
                            print(f"[RECOVERY] Failed to focus window '{target_app}': {focus_res.message}")
                except Exception as rec_err:
                    _emit(f"Recovery error: {rec_err}")
                    print(f"[RECOVERY] Recovery block error: {rec_err}")

            if res.success:
                _emit(f"✓ {step.tool} completed")
            elif not res.requires_confirmation:
                _emit(f"✗ {step.tool} failed: {res.message}")

            results.append(res.to_dict())
            
            # If still failed, halt the rest of the plan
            if not res.success:
                break
                
        return results

    def execute_step(self, step: ActionStep, progress_callback: Optional[Callable[[str], None]] = None) -> ExecutionResult:
        """Run a single ActionStep safely with PermissionManager."""
        print(f"[EXECUTOR] Received tool: {step.tool}")

        def _cb(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)
        
        handler = get_handler(step.tool)
        tool_found = handler is not None
        print(f"[EXECUTOR] Tool found: {tool_found}")
        print(f"[EXECUTOR] Arguments: {step.args}")
        _cb(f"Dispatching {step.tool}")
        
        # 1. Permission Engine Check
        if PermissionManager.requires_confirmation(step.tool, step.args):
            logger.warning(f"Confirmation required for tool {step.tool}")
            message = PermissionManager.build_confirmation_message(step.tool, step.args)
            _cb(f"Confirmation required for {step.tool}")
            
            # Store in session state and get the confirmation ID
            from agentic.memory.session_state import get_session
            confirmation_id = get_session().set_pending_action(step.tool, step.args, message)
            
            print("[EXECUTOR] Result: requires_confirmation")
            return ExecutionResult(
                success=False,
                tool=step.tool,
                message=message,
                requires_confirmation=True,
                confirmation_id=confirmation_id,
            )

        # 2. Registry Lookup
        if not tool_found:
            # Fallback for unknown/unregistered tools
            print("[EXECUTOR] Result: failure")
            return ExecutionResult(
                success=False,
                tool=step.tool,
                message=f"Tool '{step.tool}' is not supported or unregistered."
            )

        # 3. Execution
        try:
            result = handler(step.args)
            if not result.tool:
                result.tool = step.tool
            result_str = "success" if result.success else "failure"
            print(f"[EXECUTOR] Result: {result_str}")
            if result.message:
                _cb(result.message)
            return result
        except Exception as e:
            logger.exception(f"Unhandled exception in tool handler for {step.tool}")
            print("[EXECUTOR] Result: failure")
            _cb(f"Handler error: {e}")
            return ExecutionResult(
                success=False,
                tool=step.tool,
                message=f"Internal handler error: {e}"
            )

# Alias SystemExecutor for backward compatibility with existing code
SystemExecutor = DesktopExecutor
