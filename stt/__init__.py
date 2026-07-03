"""
STT (Speech-to-Text) Package
=============================

Provides audio capture and Faster-Whisper transcription.

Engines:
    - WhisperSTT        — local Faster-Whisper model (used when STT_USE_REMOTE=false)
    - RemoteWhisperSTT  — delegates to the Colab GPU server (used when STT_USE_REMOTE=true)

The active engine is selected in web/services.py → get_stt().
WhisperSTT uses lazy loading — the model is only loaded on the first transcribe() call,
so importing this module does NOT consume GPU memory in remote mode.

Usage:
    from stt.whisper_engine import WhisperSTT
    from stt.remote_whisper import RemoteWhisperSTT
    from stt.audio_capture import AudioRecorder
    from web.services import get_stt  # preferred: respects STT_USE_REMOTE config
"""

from stt.audio_capture import AudioRecorder
from stt.whisper_engine import WhisperSTT
from stt.remote_whisper import RemoteWhisperSTT

__all__ = ["WhisperSTT", "RemoteWhisperSTT", "AudioRecorder"]
