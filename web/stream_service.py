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
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


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
    plan_ms = int((time.perf_counter() - t_plan) * 1000)
    print(f"[REMOTE LLM] Plan received in {plan_ms} ms")

    plan_steps = [
        ActionStep(tool=s.tool, args=s.args)
        for s in planner_output.steps
    ]
    plan = ExecutionPlan(thought=planner_output.reasoning, steps=plan_steps, response="")

    yield _sse("planner", "completed", data=planner_output.to_dict())

    # ── Step 6: Execution ─────────────────────────────────────────────
    # We run execution in a background thread and drain the progress queue
    # so that the generator (running in the Flask request thread) can yield
    # SSE events as they arrive without blocking on the full execution.

    exec_progress_queue: queue.Queue[str | None] = queue.Queue()
    exec_results_holder: list[list[dict]] = []
    exec_error_holder: list[Exception] = []

    def _run_execution():
        try:
            executor = get_executor()

            def _progress(msg: str) -> None:
                exec_progress_queue.put(msg)

            results = []
            for idx, step in enumerate(plan_steps, 1):
                _progress(f"Step {idx}/{len(plan_steps)}: {step.tool}")
                res_step = executor.execute_step(step, progress_callback=_progress)
                results.append(res_step.to_dict())

                if res_step.requires_confirmation:
                    _progress(f"__REQUIRES_CONFIRMATION__:{res_step.confirmation_id}:{res_step.message}")
                    # Handle remaining plan via executor.execute() for PendingActionManager
                    remaining_plan = ExecutionPlan(
                        thought=plan.thought,
                        steps=plan_steps[idx - 1:],
                        response="",
                    )
                    full_results = executor.execute(remaining_plan, progress_callback=_progress)
                    exec_results_holder.append(full_results)
                    exec_progress_queue.put(None)  # sentinel
                    return

                if not res_step.success:
                    _progress(f"Step failed — triggering recovery replan")
                    remaining_plan = ExecutionPlan(
                        thought=plan.thought,
                        steps=plan_steps[idx - 1:],
                        response="",
                    )
                    full_results = executor.execute(remaining_plan, progress_callback=_progress)
                    exec_results_holder.append(full_results)
                    exec_progress_queue.put(None)  # sentinel
                    return

            exec_results_holder.append(results)
        except Exception as exc:
            exec_error_holder.append(exc)
        finally:
            exec_progress_queue.put(None)  # sentinel — always signal done

    exec_thread = threading.Thread(target=_run_execution, daemon=True)
    exec_thread.start()

    # Yield "execution started" so the card appears immediately
    yield _sse("execution", "running", message="Starting execution…")

    confirmation_detected = False
    confirmation_id_val: str | None = None
    confirmation_message_val: str | None = None

    # Drain the queue until the sentinel arrives
    while True:
        try:
            msg = exec_progress_queue.get(timeout=30)
        except queue.Empty:
            # Timeout safety — break out
            break

        if msg is None:
            break  # sentinel

        # Check for confirmation marker
        if msg.startswith("__REQUIRES_CONFIRMATION__:"):
            _, conf_id, conf_msg = msg.split(":", 2)
            confirmation_detected = True
            confirmation_id_val = conf_id
            confirmation_message_val = conf_msg
            yield _sse("execution", "requires_confirmation", message=conf_msg)
            continue

        yield _sse("execution", "running", message=msg)

    exec_thread.join(timeout=5)

    if exec_error_holder:
        yield _sse("execution", "failed", message=str(exec_error_holder[0]))
        yield _sse("done", "error", data={"error": str(exec_error_holder[0])})
        return

    exec_results: list[dict] = exec_results_holder[0] if exec_results_holder else []

    # ── Confirmation fast-path ────────────────────────────────────────
    confirmation_step = next(
        (r for r in exec_results if r.get("requires_confirmation")),
        None,
    )
    if confirmation_step:
        conf_id = confirmation_step.get("confirmation_id")
        conf_message = confirmation_step.get("message", "Confirm this action?")
        conf_tool = confirmation_step.get("tool", "unknown")

        from agentic.memory.session_state import get_session as _get_session
        pending = _get_session().get_pending_confirmation()

        partial_result = {
            "transcription": transcription,
            "stt": stt_metrics,
            "intent": {"name": planner_output.intent, "confidence": round(planner_output.confidence * 100, 1)},
            "entities": command.entities,
            "planner": planner_output.to_dict(),
            "execution": exec_results,
            "speech": {"text": conf_message},
            "pipeline_time_ms": int((time.perf_counter() - pipeline_start) * 1000),
            "timestamp": datetime.now().isoformat(),
        }
        save_session(partial_result)

        yield _sse("execution", "completed", data={"steps": exec_results})
        yield _sse("done", "requires_confirmation", data={
            "status": "requires_confirmation",
            "transcription": transcription,
            "confirmation": {
                "id": conf_id,
                "message": conf_message,
                "tool": conf_tool,
                "args": pending["args"] if pending else {},
                "remaining_seconds": pending["remaining_seconds"] if pending else 60,
            },
            "intent": {"name": planner_output.intent, "confidence": round(planner_output.confidence * 100, 1)},
            "entities": command.entities,
            "planner": planner_output.to_dict(),
            "pipeline_time_ms": int((time.perf_counter() - pipeline_start) * 1000),
        })
        return

    yield _sse("execution", "completed", data={"steps": exec_results})

    # ── Step 7: Response Generation + TTS ────────────────────────────
    yield _sse("response", "processing", message="Generating assistant response…")

    response_text = generate_response(exec_results)
    speech_audio_path = _generate_tts_file(response_text)

    speech_data: dict[str, Any] = {"text": response_text}
    if speech_audio_path:
        speech_data["audio_url"] = f"/static/audio/{os.path.basename(speech_audio_path)}"

    yield _sse("response", "completed", data=speech_data)

    # ── Final assembled payload ───────────────────────────────────────
    result = {
        "transcription": transcription,
        "stt": stt_metrics,
        "intent": {"name": planner_output.intent, "confidence": round(planner_output.confidence * 100, 1)},
        "entities": command.entities,
        "planner": planner_output.to_dict(),
        "execution": exec_results,
        "speech": speech_data,
        "pipeline_time_ms": int((time.perf_counter() - pipeline_start) * 1000),
        "timestamp": datetime.now().isoformat(),
    }
    save_session(result)

    yield _sse("done", "success", data=result)
