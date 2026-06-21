"""
Accuracy Metrics
=================

WER (Word Error Rate) and CER (Character Error Rate) computation
using the ``jiwer`` library.

WER formula:
    WER = (Substitutions + Insertions + Deletions) / Total Reference Words
    Accuracy = (1 - WER) × 100

CER is the character-level equivalent — especially useful for
non-English languages (Hindi, Hinglish) where word boundaries
are ambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import jiwer


# ──────────────────────────────────────────────────────────────────────
# Result types
# ──────────────────────────────────────────────────────────────────────

@dataclass
class WERResult:
    """Structured WER computation result."""

    wer: float               # Word Error Rate (0.0 – 1.0+)
    accuracy: float           # (1 - WER) × 100, clamped to [0, 100]
    substitutions: int
    insertions: int
    deletions: int
    hits: int                 # correct words
    reference_length: int     # total words in reference
    hypothesis_length: int    # total words in hypothesis

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CERResult:
    """Structured CER computation result."""

    cer: float
    accuracy: float
    reference_length: int
    hypothesis_length: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────
# Text normalisation transforms
# ──────────────────────────────────────────────────────────────────────

# Standard jiwer transforms for fair comparison:
#   - lowercase everything
#   - remove multiple spaces
#   - strip leading/trailing whitespace
_DEFAULT_TRANSFORMS = jiwer.Compose([
    jiwer.ToLowerCase(),
    jiwer.RemoveMultipleSpaces(),
    jiwer.Strip(),
    jiwer.RemovePunctuation(),
    jiwer.ReduceToListOfListOfWords(),
])


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def compute_wer(
    reference: str,
    hypothesis: str,
    transforms: jiwer.Compose | None = None,
) -> WERResult:
    """Compute Word Error Rate between reference and hypothesis.

    Parameters
    ----------
    reference : str
        The ground-truth transcript.
    hypothesis : str
        The model-predicted transcript.
    transforms : jiwer.Compose, optional
        Text normalisation pipeline.  Defaults to lowercase + strip
        punctuation + collapse whitespace.

    Returns
    -------
    WERResult
        Structured result with WER, accuracy, and edit counts.

    Examples
    --------
    >>> result = compute_wer("hello world", "hello word")
    >>> print(f"WER: {result.wer:.2%}, Accuracy: {result.accuracy:.1f}%")
    WER: 50.00%, Accuracy: 50.0%
    """
    if not reference.strip():
        return WERResult(
            wer=1.0 if hypothesis.strip() else 0.0,
            accuracy=0.0 if hypothesis.strip() else 100.0,
            substitutions=0,
            insertions=len(hypothesis.split()) if hypothesis.strip() else 0,
            deletions=0,
            hits=0,
            reference_length=0,
            hypothesis_length=len(hypothesis.split()) if hypothesis.strip() else 0,
        )

    tx = transforms or _DEFAULT_TRANSFORMS

    # jiwer 4.0+ API: process_words returns a WordOutput dataclass
    output = jiwer.process_words(
        reference,
        hypothesis,
        reference_transform=tx,
        hypothesis_transform=tx,
    )

    wer_value = output.wer
    accuracy = max(0.0, (1 - wer_value) * 100)

    return WERResult(
        wer=round(wer_value, 6),
        accuracy=round(accuracy, 2),
        substitutions=output.substitutions,
        insertions=output.insertions,
        deletions=output.deletions,
        hits=output.hits,
        reference_length=output.substitutions + output.deletions + output.hits,
        hypothesis_length=output.substitutions + output.insertions + output.hits,
    )


def compute_cer(
    reference: str,
    hypothesis: str,
) -> CERResult:
    """Compute Character Error Rate between reference and hypothesis.

    Useful for Hindi/Hinglish where word segmentation is inconsistent.

    Parameters
    ----------
    reference : str
        The ground-truth transcript.
    hypothesis : str
        The model-predicted transcript.

    Returns
    -------
    CERResult
        Structured result with CER and accuracy.
    """
    if not reference.strip():
        return CERResult(
            cer=1.0 if hypothesis.strip() else 0.0,
            accuracy=0.0 if hypothesis.strip() else 100.0,
            reference_length=0,
            hypothesis_length=len(hypothesis),
        )

    # jiwer 4.0+ API: process_characters returns a CharacterOutput dataclass
    output = jiwer.process_characters(reference.lower(), hypothesis.lower())
    cer_value = output.cer
    accuracy = max(0.0, (1 - cer_value) * 100)

    return CERResult(
        cer=round(cer_value, 6),
        accuracy=round(accuracy, 2),
        reference_length=len(reference),
        hypothesis_length=len(hypothesis),
    )
