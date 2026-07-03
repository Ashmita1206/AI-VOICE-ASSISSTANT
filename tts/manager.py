"""
TTS Manager
===========

Orchestrates the speech generation. Automatically attempts the high-quality
Edge TTS engine and falls back to offline PyTTSx3 if network fails.
"""

import logging

from tts.schemas import SpeechRequest, SpeechResult
from tts.edge_engine import EdgeEngine
from tts.pyttsx3_engine import PyTTSx3Engine

logger = logging.getLogger(__name__)

class TTSManager:
    """Manages text-to-speech lifecycle and fallback routing."""

    def __init__(self):
        # Load Primary Engine
        try:
            self.edge_engine = EdgeEngine()
            logger.info("EdgeEngine initialized successfully.")
        except Exception as e:
            logger.warning(f"EdgeEngine failed to load: {e}")
            self.edge_engine = None

        # Load Fallback Engine
        try:
            self.fallback_engine = PyTTSx3Engine()
            logger.info("PyTTSx3Engine initialized successfully.")
        except Exception as e:
            logger.warning(f"PyTTSx3Engine failed to load: {e}")
            self.fallback_engine = None

    def speak(self, text: str) -> SpeechResult:
        """Main entry point. Speak the given text."""
        request = SpeechRequest(text=text)
        
        # 1. Try Primary Engine
        if self.edge_engine:
            logger.debug(f"Attempting to speak using edge-tts: {text}")
            result = self.edge_engine.speak(request)
            if result.success:
                return result
            logger.warning(f"Edge TTS failed ({result.error_message}). Attempting fallback.")

        # 2. Try Fallback Engine
        if self.fallback_engine:
            logger.debug(f"Attempting to speak using pyttsx3: {text}")
            result = self.fallback_engine.speak(request)
            if result.success:
                return result
            logger.error(f"Fallback PyTTSx3 failed: {result.error_message}")
            return result
            
        # 3. No engines available
        return SpeechResult(
            success=False,
            text_spoken=text,
            engine_used="none",
            error_message="No TTS engines available."
        )
