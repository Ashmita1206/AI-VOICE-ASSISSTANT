"""
Evaluation CLI
===============

Run STT accuracy evaluation from the command line.

Usage
-----
    # Evaluate using a test data JSON file
    python -m evaluation.run_eval --data evaluation/test_data.json

    # Evaluate a single file with a known reference
    python -m evaluation.run_eval --file Recording.wav --reference "the exact transcript text"

    # Save report to custom path
    python -m evaluation.run_eval --data test_data.json --output my_report.json
"""

from __future__ import annotations

import argparse
import io
import os
import sys

# Force UTF-8 output on Windows
if sys.platform == "win32" and not hasattr(sys.stdout, "_pytest_captured_and_tear_down") and "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import logging

# Fix import path — ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s │ %(name)-25s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)

from evaluation.runner import EvaluationRunner
from evaluation.test_cases import TestCase


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="STT Accuracy Evaluation — WER/CER Report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--data", "-d",
        type=str,
        help="Path to a JSON file containing test cases.",
    )
    input_group.add_argument(
        "--file", "-f",
        type=str,
        help="Path to a single audio file to evaluate.",
    )

    parser.add_argument(
        "--reference", "-r",
        type=str,
        default=None,
        help="Reference transcript (required with --file).",
    )
    parser.add_argument(
        "--category", "-c",
        type=str,
        default="english_clean",
        help="Category label for --file mode (default: english_clean).",
    )
    parser.add_argument(
        "--language", "-l",
        type=str,
        default="en",
        help="Language code for --file mode (default: en).",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="evaluation_report.json",
        help="Output path for the JSON report (default: evaluation_report.json).",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runner = EvaluationRunner()

    if args.data:
        # Load test cases from JSON
        count = runner.load_test_cases(args.data)
        if count == 0:
            print(f"[!] No test cases loaded from {args.data}")
            sys.exit(1)

    elif args.file:
        # Single file mode
        if not args.reference:
            print("[!] --reference is required when using --file mode.")
            sys.exit(1)

        runner.add_test_case(TestCase(
            audio_path=args.file,
            reference_text=args.reference,
            language=args.language,
            category=args.category,
            description=f"Single file: {args.file}",
        ))

    # Run evaluation
    report = runner.run()

    # Display results
    runner.display_report(report)

    # Save report
    runner.save_report(report, args.output)


if __name__ == "__main__":
    main()
