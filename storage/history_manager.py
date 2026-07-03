"""
History Manager
===============

High-level API for persisting and retrieving pipeline sessions.
Handles JSON serialization of complex fields (entities, planner, execution).
"""

import json
import uuid
import logging
from typing import Any
from datetime import datetime

from storage.database import (
    insert_session,
    get_session,
    get_all_sessions,
    delete_session,
)

logger = logging.getLogger(__name__)


def save_session(pipeline_result: dict[str, Any]) -> str:
    """Persist a pipeline result as a new session.

    Parameters
    ----------
    pipeline_result : dict
        The full result dict returned by ``run_pipeline()``.

    Returns
    -------
    str
        The generated session UUID.
    """
    session_id = uuid.uuid4().hex[:12]

    stt = pipeline_result.get("stt", {})
    intent_data = pipeline_result.get("intent", {})
    speech = pipeline_result.get("speech", {})

    entry = {
        "id": session_id,
        "timestamp": pipeline_result.get("timestamp", datetime.now().isoformat()),
        "input_type": "audio",
        "audio_filename": "",
        "transcript": pipeline_result.get("transcription", ""),
        "language": stt.get("language", ""),
        "stt_confidence": stt.get("confidence", 0.0),
        "wer_accuracy": 0.0,
        "intent": intent_data.get("name", "unknown"),
        "entities": json.dumps(pipeline_result.get("entities", {})),
        "planner_output": json.dumps(pipeline_result.get("planner", {})),
        "execution_logs": json.dumps(pipeline_result.get("execution", [])),
        "response_text": speech.get("text", ""),
        "tts_audio_path": speech.get("audio_url", ""),
    }

    try:
        insert_session(entry)
        logger.info("Session %s saved.", session_id)
    except Exception as e:
        logger.error("Failed to save session: %s", e)

    return session_id


def load_all() -> list[dict[str, Any]]:
    """Load all sessions with JSON fields deserialized."""
    rows = get_all_sessions()
    return [_deserialize(r) for r in rows]


def load_one(session_id: str) -> dict[str, Any] | None:
    """Load a single session by ID, fully deserialized."""
    row = get_session(session_id)
    if row is None:
        return None
    return _deserialize(row)


def remove(session_id: str) -> bool:
    """Delete a session."""
    return delete_session(session_id)


def _deserialize(row: dict[str, Any]) -> dict[str, Any]:
    """Parse JSON string fields back into dicts/lists."""
    result = dict(row)
    for field in ("entities", "planner_output", "execution_logs"):
        val = result.get(field, "")
        if isinstance(val, str) and val:
            try:
                result[field] = json.loads(val)
            except json.JSONDecodeError:
                result[field] = {}
    return result
