"""
Edge TTS Engine
===============

Primary text-to-speech engine utilizing Microsoft Edge's neural TTS API.
Generates high-quality speech and plays it using pygame.
"""

import asyncio
import os
import tempfile
import logging
from typing import Optional

try:
    import edge_tts
    import pygame
except ImportError:
    edge_tts = None
    pygame = None

from tts.schemas import VoiceConfig, SpeechResult, SpeechRequest
from execution.schemas import ExecutionTimer

logger = logging.getLogger(__name__)

class EdgeEngine:
    """Async wrapper for edge-tts."""

    def __init__(self):
        if edge_tts is None or pygame is None:
            raise ImportError("edge-tts or pygame is not installed. EdgeEngine cannot be initialized.")
        
        # Initialize pygame mixer once
        if not pygame.mixer.get_init():
            pygame.mixer.init()

    async def _synthesize_and_play(self, text: str, config: VoiceConfig) -> None:
        """Asynchronously generate audio to a temp file and play it."""
        # Setup edge-tts communication
        communicate = edge_tts.Communicate(
            text=text,
            voice=config.voice_id,
            rate=config.rate,
            volume=config.volume,
            pitch=config.pitch
        )
        
        # Create temp file that works on both Windows and Linux securely
        fd, temp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        
        try:
            # Generate the MP3
            await communicate.save(temp_path)
            
            # Play the MP3 via pygame
            pygame.mixer.music.load(temp_path)
            pygame.mixer.music.play()
            
            # Wait for playback to finish
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)
                
            # Unload the file so we can delete it
            pygame.mixer.music.unload()
            
        finally:
            # Clean up the temp file
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception as e:
                    logger.debug(f"Failed to remove temp audio file {temp_path}: {e}")

    def speak(self, request: SpeechRequest) -> SpeechResult:
        """Synchronous wrapper to synthesize and play text."""
        config = request.config or VoiceConfig()
        
        with ExecutionTimer() as timer:
            try:
                # Run the async code synchronously
                asyncio.run(self._synthesize_and_play(request.text, config))
                
                return SpeechResult(
                    success=True,
                    text_spoken=request.text,
                    engine_used="edge-tts",
                    execution_time_ms=timer.elapsed_ms
                )
            except asyncio.TimeoutError:
                 return SpeechResult(
                    success=False,
                    text_spoken=request.text,
                    engine_used="edge-tts",
                    execution_time_ms=timer.elapsed_ms,
                    error_message="Network timeout reaching Edge TTS API."
                )
            except Exception as e:
                logger.error(f"EdgeEngine failed: {e}")
                return SpeechResult(
                    success=False,
                    text_spoken=request.text,
                    engine_used="edge-tts",
                    execution_time_ms=timer.elapsed_ms,
                    error_message=str(e)
                )
