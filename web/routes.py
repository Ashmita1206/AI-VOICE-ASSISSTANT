"""
Flask API Routes
================

Defines all HTTP endpoints for the voice assistant web UI.
"""

import os
import tempfile
import logging

from flask import Blueprint, request, jsonify, Response, stream_with_context

from web.services import run_pipeline, get_health
from web.stream_service import run_pipeline_stream
from web.confirm_service import handle_confirm, get_pending_confirmation
from storage.history_manager import load_all, load_one, remove

logger = logging.getLogger(__name__)

api = Blueprint("api", __name__)


@api.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify(get_health())


@api.route("/transcribe", methods=["POST"])
def transcribe():
    """Receive audio and run the full pipeline."""
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided."}), 400

    audio_file = request.files["audio"]

    suffix = ".wav"
    if audio_file.filename and "." in audio_file.filename:
        suffix = "." + audio_file.filename.rsplit(".", 1)[1].lower()

    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)

    try:
        audio_file.save(temp_path)
        result = run_pipeline(temp_path)
        return jsonify(result)
    except Exception as e:
        logger.exception("Pipeline error")
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@api.route("/transcribe_stream", methods=["POST"])
def transcribe_stream():
    """Receive audio and stream pipeline progress as Server-Sent Events."""
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided."}), 400

    audio_file = request.files["audio"]

    suffix = ".wav"
    if audio_file.filename and "." in audio_file.filename:
        suffix = "." + audio_file.filename.rsplit(".", 1)[1].lower()

    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)

    try:
        audio_file.save(temp_path)
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"error": str(e)}), 500

    def generate_and_cleanup():
        try:
            yield from run_pipeline_stream(temp_path)
        except Exception as exc:
            logger.exception("Streaming pipeline error")
            import json
            yield f'data: {{"stage":"done","status":"error","message":{json.dumps(str(exc))}}}\n\n'
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    return Response(
        stream_with_context(generate_and_cleanup()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@api.route("/history", methods=["GET"])
def history():
    """Return all sessions from persistent storage."""
    return jsonify(load_all())


@api.route("/session/<session_id>", methods=["GET"])
def session_detail(session_id):
    """Return a single session by ID."""
    session = load_one(session_id)
    if session is None:
        return jsonify({"error": "Session not found."}), 404
    return jsonify(session)


@api.route("/session/<session_id>", methods=["DELETE"])
def session_delete(session_id):
    """Delete a session by ID."""
    deleted = remove(session_id)
    if deleted:
        return jsonify({"status": "deleted"})
    return jsonify({"error": "Session not found."}), 404


@api.route("/speak", methods=["POST"])
def speak():
    """Text-to-speech only endpoint."""
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "No text provided."}), 400

    from web.services import _generate_tts_file
    path = _generate_tts_file(text)
    if path:
        filename = os.path.basename(path)
        return jsonify({"audio_url": f"/static/audio/{filename}"})
    return jsonify({"error": "TTS generation failed."}), 500


# ══════════════════════════════════════════════════════════════════════
# Confirmation Endpoints
# ══════════════════════════════════════════════════════════════════════

@api.route("/confirm", methods=["POST"])
def confirm():
    """Handle a user's confirmation decision (proceed or cancel).

    Request body:
        {
            "confirmation_id": "<uuid>",
            "decision": "proceed" | "cancel"
        }
    """
    data = request.get_json(silent=True) or {}

    confirmation_id = data.get("confirmation_id")
    decision = data.get("decision")

    if not confirmation_id:
        return jsonify({"success": False, "message": "Missing confirmation_id."}), 400
    if decision not in ("proceed", "cancel"):
        return jsonify({"success": False, "message": "Decision must be 'proceed' or 'cancel'."}), 400

    try:
        result = handle_confirm(confirmation_id, decision)
        return jsonify(result), 200
    except Exception as e:
        logger.exception("Confirmation error")
        return jsonify({"success": False, "message": str(e)}), 500


@api.route("/pending", methods=["GET"])
def pending():
    """Return any currently pending confirmation for the frontend.

    This lets the UI restore the confirmation card after a page refresh.
    Returns null/empty if no pending action exists.
    """
    confirmation = get_pending_confirmation()
    return jsonify({"confirmation": confirmation})

