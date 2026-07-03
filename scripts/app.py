"""
AI Voice Assistant — Phase 1 CLI
=================================

Usage
-----
    # Transcribe an existing file
    python app.py --file Recording.wav

    # Record from mic for 5 seconds, then transcribe
    python app.py --record 5

    # Record until silence, then transcribe
    python app.py --listen

    # Specify output path for recording
    python app.py --record 5 --output my_audio.wav
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys

# Force UTF-8 output on Windows to avoid charmap codec errors
if sys.platform == "win32" and not hasattr(sys.stdout, "_pytest_captured_and_tear_down") and "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config
from stt.audio_capture import AudioRecorder
from stt.whisper_engine import WhisperSTT

# ── Logging setup ────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s │ %(name)-25s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("app")

console = Console(force_terminal=True)


# ── CLI argument parsing ─────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Voice Assistant — Phase 1: Audio + STT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--file", "-f",
        type=str,
        help="Path to an existing audio file to transcribe.",
    )
    input_group.add_argument(
        "--record", "-r",
        type=float,
        nargs="?",
        const=config.AUDIO_DEFAULT_DURATION,
        help="Record from mic for N seconds (default: %(const)s).",
    )
    input_group.add_argument(
        "--listen", "-l",
        action="store_true",
        help="Record from mic until silence is detected.",
    )

    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output path for recorded WAV (only with --record/--listen).",
    )

    return parser.parse_args()


# ── Pretty output ────────────────────────────────────────────────────

def display_result(result: dict) -> None:
    """Render the transcription result in a rich formatted panel."""
    # Header info table
    info_table = Table(show_header=False, box=None, padding=(0, 2))
    info_table.add_column("Key", style="bold cyan")
    info_table.add_column("Value", style="white")

    info_table.add_row("Language", f"{result['language']}  ({result['language_probability'] * 100:.1f}% confidence)")
    info_table.add_row("Audio Duration", f"{result['duration']:.1f}s")
    info_table.add_row("Processing Time", f"{result['processing_time']:.1f}s")
    info_table.add_row(
        "Speed",
        f"{result['duration'] / max(result['processing_time'], 0.01):.1f}x real-time",
    )

    console.print()
    console.print(info_table)
    console.print()

    # The transcript itself
    console.print(Panel(
        f"[bold white]{result['text']}[/bold white]",
        title="[bold green]>> Transcript[/bold green]",
        border_style="green",
        padding=(1, 2),
    ))

    # Segment details
    if result["segments"]:
        seg_table = Table(title="Segments", show_lines=True)
        seg_table.add_column("#", style="dim", width=4)
        seg_table.add_column("Start", style="cyan", width=8)
        seg_table.add_column("End", style="cyan", width=8)
        seg_table.add_column("Text", style="white")

        for seg in result["segments"]:
            seg_table.add_row(
                str(seg["id"]),
                f"{seg['start']:.1f}s",
                f"{seg['end']:.1f}s",
                seg["text"].strip(),
            )

        console.print()
        console.print(seg_table)


# ── Main ─────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    # Banner
    console.print(Panel(
        "[bold cyan]AI Voice Assistant -- Phase 1[/bold cyan]\n"
        f"[dim]Model: {config.STT_MODEL_ID}[/dim]\n"
        f"[dim]Device: {config.DEVICE} ({config.COMPUTE_TYPE})[/dim]",
        border_style="bright_blue",
    ))

    # Step 1: Obtain audio
    audio_path: str

    if args.file:
        audio_path = args.file
        console.print(f"[*] Using existing file: [bold]{audio_path}[/bold]")
    else:
        recorder = AudioRecorder()
        if args.listen:
            audio_path = recorder.record_until_silence(output_path=args.output)
        else:
            audio_path = recorder.record(
                duration=args.record, output_path=args.output
            )

    # Step 2: Transcribe
    console.print()
    console.print("[>] Transcribing with Faster-Whisper ...")
    console.print("[dim]   (first run will download the model — may take a few minutes)[/dim]")
    console.print()

    stt = WhisperSTT()
    result = stt.transcribe(audio_path)

    # Step 3: Display result
    display_result(result)

    # Step 4: Save raw result as JSON for reference
    json_path = audio_path.rsplit(".", 1)[0] + "_transcript.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    console.print(f"\n[+] Full result saved to [bold]{json_path}[/bold]")


if __name__ == "__main__":
    main()
