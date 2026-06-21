"""
Audio Capture Module
=====================

Cross-platform microphone recording using ``sounddevice``.

Provides two recording modes:

1. **Fixed-duration** — ``record(duration, output_path)``
   Records for exactly *N* seconds.

2. **Voice-activity** — ``record_until_silence(output_path)``
   Records continuously until the user stops speaking (silence
   detected for a configurable number of seconds).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import numpy as np
import sounddevice as sd
from scipy.io import wavfile

import config

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Captures audio from the default microphone.

    Parameters
    ----------
    sample_rate : int, optional
        Samples per second.  Defaults to ``config.AUDIO_SAMPLE_RATE`` (16 000).
    channels : int, optional
        Number of audio channels.  Defaults to ``config.AUDIO_CHANNELS`` (1 = mono).
    """

    def __init__(
        self,
        sample_rate: int | None = None,
        channels: int | None = None,
    ) -> None:
        self.sample_rate = sample_rate or config.AUDIO_SAMPLE_RATE
        self.channels = channels or config.AUDIO_CHANNELS
        self._verify_audio_device()

    # ── Device check ─────────────────────────────────────────────────

    def _verify_audio_device(self) -> None:
        """Log available input devices; warn if none found."""
        try:
            devices = sd.query_devices()
            default_input = sd.query_devices(kind="input")
            logger.info(
                "Default input device: %s", default_input.get("name", "Unknown")
            )
        except Exception as exc:
            logger.warning(
                "Could not query audio devices — microphone recording may "
                "fail.  Error: %s",
                exc,
            )

    # ── Fixed-duration recording ─────────────────────────────────────

    def record(
        self,
        duration: float | None = None,
        output_path: str | None = None,
    ) -> str:
        """Record audio for a fixed duration.

        Parameters
        ----------
        duration : float, optional
            Recording length in seconds.
            Defaults to ``config.AUDIO_DEFAULT_DURATION``.
        output_path : str, optional
            Where to save the WAV file.
            Defaults to ``<AUDIO_DIR>/recording_<timestamp>.wav``.

        Returns
        -------
        str
            Absolute path to the saved WAV file.
        """
        duration = duration or config.AUDIO_DEFAULT_DURATION
        output_path = output_path or self._default_output_path()

        logger.info("Recording for %.1f s  (rate=%d, ch=%d) …",
                     duration, self.sample_rate, self.channels)
        print(f"[*] Recording for {duration}s -- speak now ...")

        try:
            audio_data = sd.rec(
                int(duration * self.sample_rate),
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
            )
            sd.wait()  # block until recording finishes
        except Exception as exc:
            raise RuntimeError(
                f"Microphone recording failed: {exc}. "
                "Check that an input device is connected."
            ) from exc

        print("[OK] Recording complete.")
        return self._save_wav(audio_data, output_path)

    # ── Voice-activity recording ─────────────────────────────────────

    def record_until_silence(
        self,
        output_path: str | None = None,
        silence_threshold: float | None = None,
        silence_duration: float | None = None,
        max_duration: float = 30.0,
    ) -> str:
        """Record until sustained silence is detected.

        Parameters
        ----------
        output_path : str, optional
            Where to save the WAV file.
        silence_threshold : float, optional
            RMS level below which audio is considered silent.
        silence_duration : float, optional
            Consecutive seconds of silence required to stop.
        max_duration : float
            Safety cap to prevent infinite recording.

        Returns
        -------
        str
            Absolute path to the saved WAV file.
        """
        output_path = output_path or self._default_output_path()
        threshold = silence_threshold or config.SILENCE_THRESHOLD
        sil_dur = silence_duration or config.SILENCE_DURATION

        chunk_size = int(self.sample_rate * 0.5)  # 500 ms chunks
        frames: list[np.ndarray] = []
        silent_chunks = 0
        required_silent = int(sil_dur / 0.5)

        logger.info("Recording until silence (threshold=%.4f, sil_dur=%.1fs) …",
                     threshold, sil_dur)
        print("[*] Listening -- speak now (will stop on silence) ...")

        start_time = time.time()
        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
            ) as stream:
                while True:
                    chunk, _ = stream.read(chunk_size)
                    frames.append(chunk.copy())

                    rms = float(np.sqrt(np.mean(chunk**2)))
                    if rms < threshold:
                        silent_chunks += 1
                    else:
                        silent_chunks = 0

                    if silent_chunks >= required_silent:
                        logger.info("Silence detected — stopping.")
                        break

                    if (time.time() - start_time) >= max_duration:
                        logger.warning("Max duration (%.0fs) reached.", max_duration)
                        break

        except Exception as exc:
            raise RuntimeError(
                f"Microphone recording failed: {exc}. "
                "Check that an input device is connected."
            ) from exc

        print("[OK] Recording complete.")
        audio_data = np.concatenate(frames, axis=0)
        return self._save_wav(audio_data, output_path)

    # ── Helpers ──────────────────────────────────────────────────────

    def _save_wav(self, audio: np.ndarray, path: str) -> str:
        """Write a numpy audio array to a 16-bit WAV file."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        # Convert float32 [-1, 1] → int16
        audio_int16 = np.int16(audio * 32767)
        wavfile.write(path, self.sample_rate, audio_int16)

        size_kb = os.path.getsize(path) / 1024
        logger.info("Saved WAV: %s (%.1f KB)", path, size_kb)
        return os.path.abspath(path)

    def _default_output_path(self) -> str:
        """Generate a timestamped default filename."""
        ts = time.strftime("%Y%m%d_%H%M%S")
        return os.path.join(config.AUDIO_DIR, f"recording_{ts}.wav")
