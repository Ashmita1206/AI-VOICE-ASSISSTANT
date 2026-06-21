"""
Evaluation Runner
==================

Orchestrates end-to-end accuracy evaluation:
1. Load test cases from registry or JSON
2. Transcribe each audio file with WhisperSTT
3. Compute WER/CER per sample
4. Aggregate results by category
5. Generate rich console report + JSON export

Usage::

    runner = EvaluationRunner()
    runner.load_test_cases("evaluation/test_data.json")
    report = runner.run()
    runner.display_report(report)
    runner.save_report(report, "evaluation_report.json")
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from evaluation.metrics import compute_wer, compute_cer, WERResult, CERResult
from evaluation.test_cases import TestCase, TestCaseRegistry
from stt.whisper_engine import WhisperSTT

import config

logger = logging.getLogger(__name__)
console = Console(force_terminal=True)


# ──────────────────────────────────────────────────────────────────────
# Result types
# ──────────────────────────────────────────────────────────────────────

@dataclass
class SampleResult:
    """Result for a single test case evaluation."""

    test_case: dict          # TestCase as dict (for serialisation)
    hypothesis: str          # model transcription
    wer_result: dict         # WERResult as dict
    cer_result: dict         # CERResult as dict
    transcription_time: float
    status: str = "success"  # "success" | "error" | "skipped"
    error_message: str = ""


@dataclass
class CategorySummary:
    """Aggregated results for a category."""

    category: str
    sample_count: int
    avg_wer: float
    avg_accuracy: float
    avg_cer: float
    avg_cer_accuracy: float
    min_accuracy: float
    max_accuracy: float
    total_time: float


@dataclass
class EvaluationReport:
    """Complete evaluation report."""

    model_id: str
    device: str
    compute_type: str
    total_samples: int
    successful_samples: int
    failed_samples: int
    total_time: float
    sample_results: list[dict]
    category_summaries: list[dict]
    overall_wer: float
    overall_accuracy: float
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────
# Evaluation Runner
# ──────────────────────────────────────────────────────────────────────

class EvaluationRunner:
    """Runs accuracy evaluation across test cases.

    Parameters
    ----------
    stt : WhisperSTT, optional
        An existing STT engine instance. If None, one will be
        created with default config.
    """

    def __init__(self, stt: WhisperSTT | None = None) -> None:
        self.stt = stt or WhisperSTT()
        self.registry = TestCaseRegistry()

    def load_test_cases(self, json_path: str) -> int:
        """Load test cases from a JSON file.

        Returns the number of cases loaded.
        """
        return self.registry.load_from_json(json_path)

    def add_test_case(self, test_case: TestCase) -> None:
        """Add a single test case."""
        self.registry.add(test_case)

    # ── Main evaluation loop ─────────────────────────────────────────

    def run(self) -> EvaluationReport:
        """Execute evaluation on all valid test cases.

        Returns
        -------
        EvaluationReport
            Complete report with per-sample and aggregate results.
        """
        valid_cases = self.registry.get_valid()

        if not valid_cases:
            console.print("[bold red]No valid test cases found![/bold red]")
            console.print(
                "[dim]Make sure audio files exist and test cases are loaded.[/dim]"
            )
            return self._empty_report()

        console.print(Panel(
            f"[bold cyan]STT Accuracy Evaluation[/bold cyan]\n"
            f"[dim]Model: {self.stt.model_id}[/dim]\n"
            f"[dim]Device: {self.stt.device} ({self.stt.compute_type})[/dim]\n"
            f"[dim]Test cases: {len(valid_cases)}[/dim]",
            border_style="bright_blue",
        ))

        sample_results: list[SampleResult] = []
        t_start = time.perf_counter()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task_id = progress.add_task(
                "Evaluating...", total=len(valid_cases)
            )

            for i, tc in enumerate(valid_cases):
                progress.update(
                    task_id,
                    description=f"[{i+1}/{len(valid_cases)}] {os.path.basename(tc.audio_path)}"
                )

                result = self._evaluate_single(tc)
                sample_results.append(result)
                progress.advance(task_id)

        total_time = time.perf_counter() - t_start

        # Build report
        report = self._build_report(sample_results, total_time)
        return report

    # ── Single sample evaluation ─────────────────────────────────────

    def _evaluate_single(self, tc: TestCase) -> SampleResult:
        """Transcribe one test case and compute metrics."""
        try:
            t0 = time.perf_counter()
            transcription = self.stt.transcribe(tc.audio_path)
            t_elapsed = time.perf_counter() - t0

            hypothesis = transcription["text"]

            wer_result = compute_wer(tc.reference_text, hypothesis)
            cer_result = compute_cer(tc.reference_text, hypothesis)

            logger.info(
                "  [%s] WER=%.2f%% Accuracy=%.1f%%  — %s",
                tc.category,
                wer_result.wer * 100,
                wer_result.accuracy,
                os.path.basename(tc.audio_path),
            )

            return SampleResult(
                test_case=tc.to_dict(),
                hypothesis=hypothesis,
                wer_result=wer_result.to_dict(),
                cer_result=cer_result.to_dict(),
                transcription_time=round(t_elapsed, 3),
            )

        except Exception as exc:
            logger.error(
                "Failed to evaluate %s: %s", tc.audio_path, exc
            )
            return SampleResult(
                test_case=tc.to_dict(),
                hypothesis="",
                wer_result={"wer": 1.0, "accuracy": 0.0},
                cer_result={"cer": 1.0, "accuracy": 0.0},
                transcription_time=0.0,
                status="error",
                error_message=str(exc),
            )

    # ── Report building ──────────────────────────────────────────────

    def _build_report(
        self,
        results: list[SampleResult],
        total_time: float,
    ) -> EvaluationReport:
        """Aggregate per-sample results into a structured report."""

        successful = [r for r in results if r.status == "success"]
        failed = [r for r in results if r.status != "success"]

        # Category summaries
        categories: dict[str, list[SampleResult]] = {}
        for r in successful:
            cat = r.test_case.get("category", "unknown")
            categories.setdefault(cat, []).append(r)

        summaries: list[CategorySummary] = []
        for cat, cat_results in sorted(categories.items()):
            wers = [r.wer_result["wer"] for r in cat_results]
            accs = [r.wer_result["accuracy"] for r in cat_results]
            cers = [r.cer_result["cer"] for r in cat_results]
            cer_accs = [r.cer_result["accuracy"] for r in cat_results]
            times = [r.transcription_time for r in cat_results]

            summaries.append(CategorySummary(
                category=cat,
                sample_count=len(cat_results),
                avg_wer=round(sum(wers) / len(wers), 4),
                avg_accuracy=round(sum(accs) / len(accs), 2),
                avg_cer=round(sum(cers) / len(cers), 4),
                avg_cer_accuracy=round(sum(cer_accs) / len(cer_accs), 2),
                min_accuracy=round(min(accs), 2),
                max_accuracy=round(max(accs), 2),
                total_time=round(sum(times), 3),
            ))

        # Overall
        if successful:
            all_wers = [r.wer_result["wer"] for r in successful]
            overall_wer = round(sum(all_wers) / len(all_wers), 4)
            overall_accuracy = round((1 - overall_wer) * 100, 2)
        else:
            overall_wer = 1.0
            overall_accuracy = 0.0

        return EvaluationReport(
            model_id=self.stt.model_id,
            device=self.stt.device,
            compute_type=self.stt.compute_type,
            total_samples=len(results),
            successful_samples=len(successful),
            failed_samples=len(failed),
            total_time=round(total_time, 3),
            sample_results=[asdict(r) for r in results],
            category_summaries=[asdict(s) for s in summaries],
            overall_wer=overall_wer,
            overall_accuracy=overall_accuracy,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

    def _empty_report(self) -> EvaluationReport:
        return EvaluationReport(
            model_id=self.stt.model_id,
            device=self.stt.device,
            compute_type=self.stt.compute_type,
            total_samples=0,
            successful_samples=0,
            failed_samples=0,
            total_time=0.0,
            sample_results=[],
            category_summaries=[],
            overall_wer=0.0,
            overall_accuracy=0.0,
        )

    # ── Display ──────────────────────────────────────────────────────

    @staticmethod
    def display_report(report: EvaluationReport) -> None:
        """Render the evaluation report as rich tables in the terminal."""

        console.print()

        # ── Category summary table ───────────────────────────────────
        cat_table = Table(
            title="[bold]Accuracy by Category[/bold]",
            show_lines=True,
        )
        cat_table.add_column("Category", style="bold cyan", width=16)
        cat_table.add_column("Samples", style="white", justify="center", width=8)
        cat_table.add_column("Avg WER", style="yellow", justify="center", width=10)
        cat_table.add_column("Accuracy", style="green bold", justify="center", width=10)
        cat_table.add_column("CER", style="yellow", justify="center", width=10)
        cat_table.add_column("Min Acc", style="dim", justify="center", width=10)
        cat_table.add_column("Max Acc", style="dim", justify="center", width=10)

        for s in report.category_summaries:
            s_obj = CategorySummary(**s) if isinstance(s, dict) else s

            # Color-code accuracy
            acc = s_obj.avg_accuracy
            if acc >= 90:
                acc_style = "[bold green]"
            elif acc >= 75:
                acc_style = "[bold yellow]"
            else:
                acc_style = "[bold red]"

            cat_table.add_row(
                s_obj.category,
                str(s_obj.sample_count),
                f"{s_obj.avg_wer * 100:.1f}%",
                f"{acc_style}{acc:.1f}%[/]",
                f"{s_obj.avg_cer * 100:.1f}%",
                f"{s_obj.min_accuracy:.1f}%",
                f"{s_obj.max_accuracy:.1f}%",
            )

        console.print(cat_table)

        # ── Per-sample detail table ──────────────────────────────────
        console.print()
        detail_table = Table(
            title="[bold]Per-Sample Results[/bold]",
            show_lines=True,
        )
        detail_table.add_column("#", style="dim", width=4)
        detail_table.add_column("File", style="cyan", width=20)
        detail_table.add_column("Category", style="white", width=14)
        detail_table.add_column("WER", style="yellow", justify="center", width=8)
        detail_table.add_column("Accuracy", style="green", justify="center", width=10)
        detail_table.add_column("Status", justify="center", width=8)

        for i, sr in enumerate(report.sample_results, 1):
            audio_path = sr["test_case"].get("audio_path", "?")
            filename = os.path.basename(audio_path)
            status_icon = "✅" if sr["status"] == "success" else "❌"

            wer_val = sr["wer_result"].get("wer", 0)
            acc_val = sr["wer_result"].get("accuracy", 0)

            detail_table.add_row(
                str(i),
                filename[:20],
                sr["test_case"].get("category", "?"),
                f"{wer_val * 100:.1f}%",
                f"{acc_val:.1f}%",
                status_icon,
            )

        console.print(detail_table)

        # ── Overall summary ──────────────────────────────────────────
        console.print()
        console.print(Panel(
            f"[bold white]Overall Accuracy: "
            f"[bold {'green' if report.overall_accuracy >= 90 else 'yellow' if report.overall_accuracy >= 75 else 'red'}]"
            f"{report.overall_accuracy:.1f}%[/][/bold white]\n"
            f"[dim]Overall WER: {report.overall_wer * 100:.1f}%  │  "
            f"Samples: {report.successful_samples}/{report.total_samples}  │  "
            f"Time: {report.total_time:.1f}s[/dim]",
            title="[bold green]>> Evaluation Summary[/bold green]",
            border_style="green",
        ))

    # ── Export ────────────────────────────────────────────────────────

    @staticmethod
    def save_report(report: EvaluationReport, path: str) -> str:
        """Save the evaluation report as JSON.

        Returns the absolute path to the saved file.
        """
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        console.print(f"\n[+] Report saved to [bold]{path}[/bold]")
        return os.path.abspath(path)
