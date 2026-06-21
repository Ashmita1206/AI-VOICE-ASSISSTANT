"""
Evaluation Package
===================

Provides accuracy evaluation for STT transcription using
Word Error Rate (WER) and Character Error Rate (CER).

Usage:
    from evaluation.metrics import compute_wer, compute_cer
    from evaluation.runner import EvaluationRunner
"""

from evaluation.metrics import compute_wer, compute_cer

__all__ = ["compute_wer", "compute_cer"]
