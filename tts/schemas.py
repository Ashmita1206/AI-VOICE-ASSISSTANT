"""
TTS Schemas
===========

Data contracts for the Text-to-Speech sub-system.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class VoiceConfig:
    """Configuration for speech synthesis."""
    # Edge-tts standard voice ID. For Jarvis, we default to a standard clear American male voice.
    voice_id: str = "en-US-ChristopherNeural" 
    # Relative speed. e.g. "+10%", "-5%"
    rate: str = "+0%"
    # Relative volume. e.g. "+20%"
    volume: str = "+0%"
    # Relative pitch. e.g. "+5Hz"
    pitch: str = "+0Hz"


@dataclass
class SpeechRequest:
    """Request payload sent to the TTS Manager."""
    text: str
    config: Optional[VoiceConfig] = None
    priority: int = 1


@dataclass
class SpeechResult:
    """Result returned by the TTS Manager after audio playback finishes."""
    success: bool
    text_spoken: str
    engine_used: str  # e.g., 'edge-tts' or 'pyttsx3'
    execution_time_ms: int = 0
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "text_spoken": self.text_spoken,
            "engine_used": self.engine_used,
            "execution_time_ms": self.execution_time_ms,
            "error_message": self.error_message,
        }
