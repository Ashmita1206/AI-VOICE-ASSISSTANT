"""
PyTTSx3 Engine (Fallback)
=========================

Offline, system-native text-to-speech fallback engine.
Used if the network is unavailable for Edge TTS.
"""

import logging
from typing import Optional

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

from tts.schemas import VoiceConfig, SpeechResult, SpeechRequest
from execution.schemas import ExecutionTimer

logger = logging.getLogger(__name__)

class PyTTSx3Engine:
    """Offline wrapper for pyttsx3."""

    def __init__(self):
        if pyttsx3 is None:
            raise ImportError("pyttsx3 is not installed. PyTTSx3Engine cannot be initialized.")
        
        try:
            self.engine = pyttsx3.init()
            # Try to pick a decent voice (usually 1 is female, 0 is male on Windows)
            voices = self.engine.getProperty('voices')
            if len(voices) > 1:
                self.engine.setProperty('voice', voices[1].id)
            self.engine.setProperty('rate', 160)  # Slightly slower than default 200
        except Exception as e:
            logger.error(f"Failed to initialize pyttsx3: {e}")
            self.engine = None

    def speak(self, request: SpeechRequest) -> SpeechResult:
        """Synthesize and play text synchronously."""
        if not self.engine:
            return SpeechResult(
                success=False,
                text_spoken=request.text,
                engine_used="pyttsx3",
                execution_time_ms=0,
                error_message="pyttsx3 engine not initialized."
            )
            
        with ExecutionTimer() as timer:
            try:
                self.engine.say(request.text)
                self.engine.runAndWait()
                
                return SpeechResult(
                    success=True,
                    text_spoken=request.text,
                    engine_used="pyttsx3",
                    execution_time_ms=timer.elapsed_ms
                )
            except Exception as e:
                logger.error(f"PyTTSx3Engine failed: {e}")
                return SpeechResult(
                    success=False,
                    text_spoken=request.text,
                    engine_used="pyttsx3",
                    execution_time_ms=timer.elapsed_ms,
                    error_message=str(e)
                )
