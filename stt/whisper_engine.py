"""
Faster-Whisper Transcription Engine
=====================================

Wraps the ``faster-whisper`` library around the
**deepdml/faster-whisper-large-v3-turbo-ct2** model.

Key design decisions
--------------------
* **Lazy loading** — the model is only downloaded / loaded into memory
  the first time ``transcribe()`` is called.  This keeps import time fast
  and avoids blocking the main thread on startup.
* **Structured output** — every transcription returns a typed ``dict``
  with text, segments, language info, and duration so downstream
  components have a uniform contract to rely on.
* **Robust error handling** — file-not-found, corrupt audio, and model
  load failures are all caught and surfaced as clear error messages.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

from faster_whisper import WhisperModel

import config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Transcription result type
# ──────────────────────────────────────────────────────────────────────
TranscriptionResult = dict[str, Any]
"""
Shape:
{
    "text":                  str,   # cleaned final transcript
    "raw_text":              str,   # unmodified model output
    "segments":              list,  # list of segment dicts (start, end, text)
    "language":              str,   # detected language code, e.g. "en"
    "language_probability":  float, # confidence in detected language
    "duration":              float, # audio duration in seconds
    "processing_time":       float, # wall-clock transcription time
}
"""


class WhisperSTT:
    """High-level Faster-Whisper transcription interface.

    Parameters
    ----------
    model_id : str, optional
        Hugging Face model identifier.  Defaults to the value in
        ``config.STT_MODEL_ID``.
    device : str, optional
        ``"cuda"`` or ``"cpu"``.  Defaults to auto-detected value.
    compute_type : str, optional
        ``"float16"`` (GPU) or ``"int8"`` (CPU).  Defaults to
        auto-detected value.
    """

    def __init__(
        self,
        model_id: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
    ) -> None:
        self.model_id = model_id or config.STT_MODEL_ID
        self.device = device or config.DEVICE
        self.compute_type = compute_type or config.COMPUTE_TYPE

        # Will be initialised lazily on first transcribe() call.
        self._model: WhisperModel | None = None

        logger.info(
            "WhisperSTT configured — model=%s  device=%s  compute=%s",
            self.model_id,
            self.device,
            self.compute_type,
        )

    # ── Model loading ────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Download (if needed) and load the Whisper model."""
        logger.info("Loading Faster-Whisper model '%s' …", self.model_id)
        load_start = time.perf_counter()

        try:
            self._model = WhisperModel(
                self.model_id,
                device=self.device,
                compute_type=self.compute_type,
            )
        except Exception as exc:
            logger.error("Failed to load model: %s", exc)
            raise RuntimeError(
                f"Could not load Faster-Whisper model '{self.model_id}'. "
                f"Device={self.device}, ComputeType={self.compute_type}. "
                f"Original error: {exc}"
            ) from exc

        elapsed = time.perf_counter() - load_start
        logger.info("Model loaded in %.2f s", elapsed)

    @property
    def model(self) -> WhisperModel:
        """Return the loaded model, initialising it lazily."""
        if self._model is None:
            self._load_model()
        assert self._model is not None
        return self._model

    # ── Transcription ────────────────────────────────────────────────

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        """Transcribe an audio file and return a structured result.

        Parameters
        ----------
        audio_path : str
            Path to a WAV/MP3/FLAC/OGG audio file.

        Returns
        -------
        TranscriptionResult
            See module-level docstring for shape.

        Raises
        ------
        FileNotFoundError
            If *audio_path* does not exist.
        RuntimeError
            If transcription fails for any reason.
        """
        # --- Validate input ---
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        logger.info("Transcribing '%s' …", audio_path)
        t_start = time.perf_counter()

        try:
            segments_gen, info = self.model.transcribe(
                audio_path,
                beam_size=config.STT_BEAM_SIZE,
                vad_filter=config.STT_VAD_FILTER,
            )

            # Materialise the generator into a list of dicts
            segments: list[dict[str, Any]] = []
            raw_parts: list[str] = []
            for seg in segments_gen:
                segments.append(
                    {
                        "id": seg.id,
                        "start": round(seg.start, 3),
                        "end": round(seg.end, 3),
                        "text": seg.text,
                    }
                )
                raw_parts.append(seg.text)

        except Exception as exc:
            logger.error("Transcription failed: %s", exc)
            raise RuntimeError(
                f"Faster-Whisper transcription failed for '{audio_path}': {exc}"
            ) from exc

        processing_time = time.perf_counter() - t_start
        raw_text = " ".join(raw_parts).strip()
        cleaned = self._clean_text(raw_text)

        result: TranscriptionResult = {
            "text": cleaned,
            "raw_text": raw_text,
            "segments": segments,
            "language": info.language,
            "language_probability": round(info.language_probability, 4),
            "duration": round(info.duration, 3),
            "processing_time": round(processing_time, 3),
        }

        logger.info(
            "Transcription complete — lang=%s (%.1f%%)  duration=%.1fs  "
            "processed_in=%.1fs",
            result["language"],
            result["language_probability"] * 100,
            result["duration"],
            result["processing_time"],
        )
        return result

    # ── Text cleaning ────────────────────────────────────────────────

    @staticmethod
    def _clean_text(text: str) -> str:
        """Normalise whitespace and light punctuation cleanup.

        This intentionally does *not* alter casing or remove
        punctuation — downstream NLU components may rely on it.
        """
        # Collapse multiple spaces / newlines into a single space
        text = re.sub(r"\s+", " ", text).strip()
        # Remove leading/trailing whitespace around punctuation
        text = re.sub(r"\s+([.,!?;:])", r"\1", text)
        return text
