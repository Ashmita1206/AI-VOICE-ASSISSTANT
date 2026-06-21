"""
STT (Speech-to-Text) Package
=============================

Provides audio capture and Faster-Whisper transcription.

Usage:
    from stt.whisper_engine import WhisperSTT
    from stt.audio_capture import AudioRecorder
"""

from stt.whisper_engine import WhisperSTT
from stt.audio_capture import AudioRecorder

__all__ = ["WhisperSTT", "AudioRecorder"]
