"""
SSE Streaming Pipeline Service
================================

Mirrors run_pipeline() from services.py but yields Server-Sent Events (SSE)
at each stage boundary so the UI can progressively reveal results.

Wire format (each event is a separate flush):
    data: {"stage":"transcript","status":"completed","data":{...}}\n\n

Stages emitted (in order):
    transcript      → STT done
    intent          → IntentClassifier done
    entities        → Entity data ready (from classifier result)
    discovery       → System context compiled for planner
    planner         → PlannerManager.plan() done
    execution       → status:"running" per sub-step; status:"completed" when all done
    response        → Response text + audio URL ready
    done            → Final assembled payload (or no_speech / requires_confirmation)
"""

from __future__ import annotations

import json
import os
import sys
import io
import time
import logging
import queue
import threading
from datetime import datetime
from typing import Any, Generator

# Prevent UnicodeEncodeError on Windows stdout
if sys.platform.startswith("win") and "pytest" not in sys.modules:
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

import config
from web.services import get_stt, get_classifier, get_executor, _generate_tts_file
from tts.response_generator import generate_response
from storage.history_manager import save_session
from execution.registry import get_handler, load_all_tools
from agentic.llm.schemas import PlannerOutput

# Load registered tools
load_all_tools()

def validate_execution_plan(planner_output: PlannerOutput) -> str | None:
    """Validate the PlannerOutput execution plan.
    
    Returns a string reason if validation fails, or None if validation succeeds.
    """
    if not planner_output:
        return "Planner JSON is missing or null."
        
    if not hasattr(planner_output, "steps") or planner_output.steps is None:
        return "Steps array does not exist in the plan."
        
    if len(planner_output.steps) == 0:
        return "Planner produced no executable steps."
        
    seen_steps = set()
    for idx, s in enumerate(planner_output.steps, 1):
        if not s.tool:
            return f"Step {idx} is missing a tool name."
        if s.args is None:
            return f"Step {idx} ({s.tool}) is missing arguments."
        if not getattr(s, "description", None) and not s.description:
            # We assign step description fallback here
            s.description = f"Execute {s.tool.replace('_', ' ')}"
            
        # Verify tool is registered
        handler = get_handler(s.tool)
        if handler is None:
            return f"Tool '{s.tool}' in step {idx} is not registered."
            
        step_fingerprint = (s.tool, json.dumps(s.args, sort_keys=True))
        if step_fingerprint in seen_steps:
            return f"Duplicate step detected: {s.tool} with args {s.args}."
        seen_steps.add(step_fingerprint)
        
    return None

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# SSE helpers
# ══════════════════════════════════════════════════════════════════════

def _sse(stage: str, status: str, data: Any = None, message: str | None = None) -> str:
    """Encode one SSE event as a string to be flushed."""
    payload: dict[str, Any] = {"stage": stage, "status": status}
    if data is not None:
        payload["data"] = data
    if message is not None:
        payload["message"] = message
    serialized = json.dumps(payload, ensure_ascii=False)
    safe_serialized = serialized.encode("ascii", "replace").decode("ascii")
    print(f"[DEBUG BACKEND RESPONSE] Stage: {stage} | Status: {status} | Payload: {safe_serialized[:1000]}")
    return f"data: {serialized}\n\n"


# ══════════════════════════════════════════════════════════════════════
# Main streaming generator
# ══════════════════════════════════════════════════════════════════════

def run_pipeline_stream(audio_path: str) -> Generator[str, None, None]:
    """
    Generator that runs the full pipeline and yields SSE events.

    Usage in Flask route:
        return Response(
            stream_with_context(run_pipeline_stream(temp_path)),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    """
    pipeline_start = time.perf_counter()

    # ── Step 1: STT ──────────────────────────────────────
    yield _sse("transcript", "processing", message="Transcribing audio…")

    stt = get_stt()
    mode_label = "REMOTE" if config.STT_USE_REMOTE else "LOCAL"
    print(f"[VOICE] Sending audio to {mode_label} STT…")
    t_stt = time.perf_counter()
    stt_result = stt.transcribe(audio_path)
    stt_ms = int((time.perf_counter() - t_stt) * 1000)
    print(f"[REMOTE STT] Upload complete | Latency: {stt_ms} ms")
    transcription = stt_result.get("text", "")
    print(f"[REMOTE STT] Text: \"{transcription[:120]}\"")

    stt_metrics = {
        "model": config.STT_MODEL_ID,
        "device": config.DEVICE,
        "compute_type": config.COMPUTE_TYPE,
        "language": stt_result.get("language", ""),
        "confidence": round(stt_result.get("language_probability", 0) * 100, 1),
        "processing_time_ms": int(stt_result.get("processing_time", 0) * 1000),
    }

    # Update app context silently
    if transcription.strip():
        try:
            from agentic.memory.app_context import AppContextManager, get_active_window_info
            from agentic.memory.session_state import get_session
            info = get_active_window_info()
            if info["active_app"]:
                AppContextManager.set_context(
                    active_app=info["active_app"],
                    window_handle=info["window_handle"],
                    last_command=transcription,
                )
                get_session().set_context(app=info["active_app"])
        except Exception:
            pass

    yield _sse("transcript", "completed", data={
        "text": transcription,
        "stt": stt_metrics,
    })

    # ── Silent-audio fast-path ────────────────────────────────────────
    if not transcription.strip():
        no_speech_response = "I didn't catch that. Could you try again?"
        yield _sse("response", "completed", data={"text": no_speech_response})
        yield _sse("done", "no_speech", data={
            "transcription": "",
            "stt": stt_metrics,
            "intent": {"name": "unknown", "confidence": 0},
            "entities": {},
            "planner": {"thought": "", "steps": []},
            "execution": [],
            "speech": {"text": no_speech_response},
            "pipeline_time_ms": int((time.perf_counter() - pipeline_start) * 1000),
        })
        return

    # ── Step 2: Intent Classification ──────────────────────────
    yield _sse("intent", "processing", message="Classifying intent…")

    classifier = get_classifier()
    t_intent = time.perf_counter()
    command = classifier.classify(transcription)
    intent_ms = int((time.perf_counter() - t_intent) * 1000)
    print(f"[INTENT] Detected: {command.intent} (Confidence: {round(command.confidence * 100, 1)}%)  [{intent_ms} ms]")
    print(f"[ENTITY] Detected: {command.entities}")
    intent_data = {
        "name": command.intent,
        "confidence": round(command.confidence * 100, 1),
    }
    yield _sse("intent", "completed", data=intent_data)

    # ── Step 3: Entities (derived from classifier result) ────────────
    yield _sse("entities", "completed", data={"entities": command.entities})

    # ── Step 4: Discovery / System context (feeds the planner) ───────
    yield _sse("discovery", "processing", message="Indexing system resources…")

    from agentic.discovery.manager import get_system_context
    system_context = get_system_context()
    yield _sse("discovery", "completed", message="System context ready")

    # ── Step 5: Planning ─────────────────────────────────────
    yield _sse("planner", "processing", message="Building execution plan…")
    print(f"[REMOTE LLM] Sending to planner...")
    t_plan = time.perf_counter()

    from agentic.llm.manager import get_planner_manager
    from agentic.llm.schemas import PlannerOutput
    from agentic.schemas import ExecutionPlan, ActionStep

    planner = get_planner_manager()
    planner_output: PlannerOutput = planner.plan(transcription)
    print(f"[DEBUG PLANNER OUTPUT]: {json.dumps(planner_output.to_dict(), indent=2)}")
    plan_ms = int((time.perf_counter() - t_plan) * 1000)
    print(f"[REMOTE LLM] Plan received in {plan_ms} ms")

    # ── Step 5.5: Plan Validation ───────────────────────────────────
    validation_error = validate_execution_plan(planner_output)
    plan_dict_to_dict = planner_output.to_dict()
    steps_count = len(planner_output.steps)
    permissions = plan_dict_to_dict.get("permissions", [])
    proceed_enabled = (validation_error is None)

    print("-------------------------------------------------")
    print("[BACKEND PLAN VALIDATION LOGS]")
    print(f"Planner Output: {json.dumps(plan_dict_to_dict, indent=2)}")
    print(f"Validated Plan: {proceed_enabled}")
    print(f"Steps Count: {steps_count}")
    print(f"Permissions: {permissions}")
    print(f"Proceed Enabled = {proceed_enabled}")
    if validation_error:
        print(f"Reason if false: {validation_error}")
    print("-------------------------------------------------")

    if validation_error:
        yield _sse("planner", "failed", data={
            "success": False,
            "error": validation_error
        }, message=f"Failed to generate execution plan: {validation_error}")
        yield _sse("done", "error", data={
            "status": "error",
            "success": False,
            "error": validation_error,
            "message": f"Failed to generate execution plan. Reason: {validation_error}"
        }, message=f"Failed to generate execution plan: {validation_error}")
        return

    plan_steps = [
        ActionStep(tool=s.tool, args=s.args)
        for s in planner_output.steps
    ]
    plan = ExecutionPlan(thought=planner_output.reasoning, steps=plan_steps, response="")

    yield _sse("planner", "completed", data=planner_output.to_dict())

    # ── Step 6: Full Plan Confirmation ───────────────────────────────────────
    if len(planner_output.steps) == 0:
        # Proceed directly to response generation for conversational intents
        yield _sse("response", "processing", message="Generating assistant response…")
        response_text = planner_output.reasoning or "No actions planned."
        speech_audio_path = _generate_tts_file(response_text)
        speech_data = {"text": response_text}
        if speech_audio_path:
            speech_data["audio_url"] = f"/static/audio/{os.path.basename(speech_audio_path)}"
        yield _sse("response", "completed", data=speech_data)
        if speech_audio_path:
            logger.info("Audio URL Sent")
        
        result = {
            "transcription": transcription,
            "stt": stt_metrics,
            "intent": {"name": planner_output.intent, "confidence": round(planner_output.confidence * 100, 1)},
            "entities": command.entities,
            "planner": planner_output.to_dict(),
            "execution": [],
            "speech": speech_data,
            "pipeline_time_ms": int((time.perf_counter() - pipeline_start) * 1000),
            "timestamp": datetime.now().isoformat(),
        }
        save_session(result)
        yield _sse("done", "success", data=result)
        return

    plan_dict = {
        "intent": planner_output.intent,
        "thought": planner_output.reasoning,
        "steps": [
            {"tool": s.tool, "args": s.args} for s in planner_output.steps
        ],
    }
    
    from agentic.memory.pending_action import PendingActionManager
    confirmation_id = PendingActionManager.save(plan_dict)
    
    # Infer permissions and estimated actions
    permissions = []
    estimated_actions = []
    
    for s in planner_output.steps:
        tool = s.tool
        args = s.args or {}
        
        # Map tools to permissions
        if tool in ("press_key", "type_text", "hotkey"):
            permissions.append("Keyboard Control")
        elif tool in ("click", "double_click", "right_click", "scroll", "drag"):
            permissions.append("Mouse Control")
        elif tool in ("launch_application", "focus_window", "close_window", "is_app_running", "activate_window"):
            permissions.append("Foreground Window Control")
        elif tool in ("open_browser", "open_website", "open_whatsapp"):
            permissions.append("Browser Automation")
        elif tool in ("search_inside_application", "perform_app_action"):
            permissions.append("Accessibility/UI Automation")
        elif tool in ("ocr", "locate_ui_element", "find_text", "take_screenshot"):
            permissions.append("Screen Capture")
        elif tool in ("create_file", "create_folder", "delete_file", "delete_folder", "read_directory", "list_files"):
            permissions.append("File System Access")
            
        # Human-friendly action descriptions
        if tool == "launch_application":
            estimated_actions.append(f"Open {args.get('application', 'application')}")
        elif tool == "search_inside_application":
            estimated_actions.append(f"Search for '{args.get('query', '')}'")
        elif tool == "press_key":
            estimated_actions.append(f"Press {args.get('key', '').capitalize()}")
        elif tool == "type_text":
            estimated_actions.append(f"Type '{args.get('text', '')}'")
        elif tool == "open_browser":
            estimated_actions.append("Open web browser")
        elif tool == "open_website":
            estimated_actions.append(f"Navigate to {args.get('url', 'website')}")
        elif tool == "send_whatsapp_message":
            estimated_actions.append(f"Send message to {args.get('contact', 'contact')}")
        else:
            estimated_actions.append(f"Execute {tool.replace('_', ' ')}")
            
    # Deduplicate permissions
    permissions = sorted(list(set(permissions)))
    if not permissions:
        permissions = ["System Control"]
        
    yield _sse("done", "requires_confirmation", data={
        "status": "requires_confirmation",
        "transcription": transcription,
        "confirmation": {
            "id": confirmation_id,
            "message": f"I will perform these actions to execute your request: '{transcription}'",
            "plan": planner_output.to_dict(),
            "permissions": permissions,
            "estimated_actions": estimated_actions,
            "remaining_seconds": 60,
        },
        "intent": {"name": planner_output.intent, "confidence": round(planner_output.confidence * 100, 1)},
        "entities": command.entities,
        "planner": planner_output.to_dict(),
        "pipeline_time_ms": int((time.perf_counter() - pipeline_start) * 1000),
    })


def run_confirmation_stream(confirmation_id: str, edited_steps: list[dict] | None = None) -> Generator[str, None, None]:
    """Execute the pending action plan and stream the progress as SSE."""
    from agentic.memory.pending_action import PendingActionManager
    from agentic.memory.session_state import get_session
    from execution.executor import DesktopExecutor
    from agentic.schemas import ActionStep, ExecutionPlan
    import queue
    import threading
    
    session = get_session()
    pending_data = PendingActionManager.get_pending_action()
    
    if not pending_data or pending_data.get("id") != confirmation_id:
        yield _sse("done", "error", message="Pending action timed out or not found.")
        return
        
    saved_plan = pending_data["plan"]
    
    # Use edited steps if provided, otherwise the saved steps
    steps_list = edited_steps if edited_steps is not None else saved_plan.get("steps", [])
    if not steps_list:
        PendingActionManager.clear()
        session.clear_pending_action()
        yield _sse("done", "error", message="Pending action plan is empty.")
        return
        
    # Clear pending action state
    PendingActionManager.clear()
    session.clear_pending_action()
    
    plan_steps = [
        ActionStep(tool=s["tool"], args=s["args"])
        for s in steps_list
    ]
    plan = ExecutionPlan(
        thought=saved_plan.get("thought", "Executing approved plan"),
        steps=plan_steps,
        response=""
    )
    
    yield _sse("execution", "running", message="Starting execution…")
    logger.info(f"Dispatching plan with {len(plan_steps)} steps to executor...")
    
    try:
        executor = DesktopExecutor()
        executor.bypass_confirmation = True  # Bypass individual step prompts since the entire plan is approved
    except Exception as exc:
        logger.exception("Failed to initialize DesktopExecutor")
        yield _sse("execution", "failed", message=f"Executor init failed: {exc}")
        yield _sse("done", "error", data={"error": str(exc)})
        return
    
    progress_queue: queue.Queue[str | None] = queue.Queue()
    exec_results_holder: list[list[dict]] = []
    exec_error_holder: list[Exception] = []
    
    def _run_execution():
        try:
            full_results = executor.execute(plan, progress_callback=progress_queue.put)
            exec_results_holder.append(full_results)
        except Exception as e:
            exec_error_holder.append(e)
        finally:
            progress_queue.put(None)
            
    logger.info("Starting execution background thread...")
    logger.info("Execution Started")
    exec_thread = threading.Thread(target=_run_execution, daemon=True)
    exec_thread.start()
    
    while True:
        try:
            msg = progress_queue.get(timeout=30)
        except queue.Empty:
            logger.warning("Execution queue timed out after 30s")
            break
        if msg is None:
            break
        safe_msg = msg.encode("ascii", "replace").decode("ascii") if msg else ""
        logger.info(f"Execution progress: {safe_msg}")
        yield _sse("execution", "running", message=msg)
        
    logger.info("Waiting for execution thread to finish...")
    exec_thread.join(timeout=5)
    logger.info("Execution thread finished.")
    logger.info("Execution Finished")
    
    if exec_error_holder:
        yield _sse("execution", "failed", message=str(exec_error_holder[0]))
        yield _sse("done", "error", data={"error": str(exec_error_holder[0])})
        return
        
    exec_results = exec_results_holder[0] if exec_results_holder else []
    yield _sse("execution", "completed", data={"steps": exec_results})
    
    # Step 7: Response Generation + TTS
    yield _sse("response", "processing", message="Generating assistant response…")
    
    response_text = generate_response(exec_results)
    speech_audio_path = _generate_tts_file(response_text)
    
    speech_data: dict[str, Any] = {"text": response_text}
    if speech_audio_path:
        speech_data["audio_url"] = f"/static/audio/{os.path.basename(speech_audio_path)}"
        
    yield _sse("response", "completed", data=speech_data)
    if speech_audio_path:
        logger.info("Audio URL Sent")
    
    # Add to session history
    session.add_history(
        transcript=f"[Confirmed] {saved_plan.get('thought', 'User approved execution plan')}",
        intent="execute_confirmed",
        plan=saved_plan,
        result=response_text,
    )
    
    # Save session
    result = {
        "transcription": saved_plan.get('thought', 'User approved execution plan'),
        "stt": {"model": "", "device": "", "compute_type": "", "language": "", "confidence": 100, "processing_time_ms": 0},
        "intent": {"name": saved_plan.get("intent", "execute_confirmed"), "confidence": 100},
        "entities": {},
        "planner": saved_plan,
        "execution": exec_results,
        "speech": speech_data,
        "pipeline_time_ms": 0,
        "timestamp": datetime.now().isoformat(),
    }
    save_session(result)
    yield _sse("done", "success", data=result)
