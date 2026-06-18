#!/usr/bin/env python3
"""CI evaluation runner.

Loads the golden test set, runs the RAG eval suite, compares results
against baseline metrics, and exits with code 0 (pass) or 1 (fail).

Usage:
    python -m scripts.run_eval_ci                    # compare to baseline
    python -m scripts.run_eval_ci --update-baseline  # run eval and write new baseline
    python -m scripts.run_eval_ci --generate-baseline  # run eval and save as new baseline

Environment variables (required):
    OPENROUTER_API_KEY  — for LLM-as-judge and answer generation
    GOOGLE_API_KEY      — for Gemini embeddings
    SUPABASE_URL        — Supabase project URL
    SUPABASE_SERVICE_ROLE_KEY — Supabase service key (for retrieval FTS)
    QDRANT_URL          — Qdrant vector DB URL
    QDRANT_API_KEY      — Qdrant API key
    COHERE_API_KEY      — for reranking (optional, falls back to keyword overlap)

Environment variables (optional):
    EVAL_REGRESSION_THRESHOLD — max metric drop (on 1-5 scale) before failing; default 0.5
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure the backend package is importable when run from project root
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.eval_pipeline import (
    EvalSuiteResult,
    load_golden_test_set,
    run_eval_suite,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("eval_ci")

# Paths
FIXTURES_DIR = _ROOT / "tests" / "fixtures"
GOLDEN_PATH = FIXTURES_DIR / "golden_test_set.json"
BASELINE_PATH = FIXTURES_DIR / "eval_baseline.json"

METRICS = ["faithfulness", "answer_relevance", "context_precision", "context_recall", "overall"]
REGRESSION_THRESHOLD = float(os.environ.get("EVAL_REGRESSION_THRESHOLD", "0.5"))


def load_baseline(path: Path = BASELINE_PATH) -> dict:
    """Load baseline metrics from JSON file."""
    if not path.exists():
        logger.warning("No baseline file at %s — skipping regression check", path)
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {k: data[k] for k in METRICS if k in data}


def save_baseline(suite: EvalSuiteResult, path: Path = BASELINE_PATH) -> None:
    """Write current eval metrics as the new baseline."""
    metrics = {
        "faithfulness": round(suite.avg_faithfulness, 2),
        "answer_relevance": round(suite.avg_answer_relevance, 2),
        "context_precision": round(suite.avg_context_precision, 2),
        "context_recall": round(suite.avg_context_recall, 2),
        "overall": round(suite.avg_overall, 2),
        "updated_at": datetime.now(UTC).isoformat(),
        "notes": f"Auto-updated from eval run {suite.run_id or 'ci'}",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    logger.info("Baseline updated at %s", path)


def compare_metrics(current: dict, baseline: dict) -> tuple[bool, list[str]]:
    """Compare current metrics to baseline.

    Returns:
        (passed, details) where passed is True if no regression exceeds threshold.
    """
    if not baseline:
        return True, ["No baseline found — skipping regression check."]

    passed = True
    details = []
    for metric in METRICS:
        cur = current.get(metric, 0.0)
        base = baseline.get(metric, 0.0)
        delta = cur - base
        if delta < -REGRESSION_THRESHOLD:
            passed = False
            details.append(f"  FAIL  {metric}: {cur:.2f} (baseline {base:.2f}, delta {delta:+.2f})")
        elif delta < 0:
            details.append(f"  WARN  {metric}: {cur:.2f} (baseline {base:.2f}, delta {delta:+.2f})")
        else:
            details.append(f"  PASS  {metric}: {cur:.2f} (baseline {base:.2f}, delta {delta:+.2f})")
    return passed, details


def format_summary(suite: EvalSuiteResult, baseline: dict, passed: bool, details: list[str]) -> str:
    """Build a human-readable summary string."""
    lines = [
        "=" * 60,
        "  RAG Eval CI — Results Summary",
        "=" * 60,
        f"  Run ID:       {suite.run_id or 'N/A'}",
        f"  Test cases:   {suite.total_cases}",
        f"  Started:      {suite.started_at}",
        f"  Completed:    {suite.completed_at}",
        "-" * 60,
        "  Metric Comparison (threshold: {:.1f})".format(REGRESSION_THRESHOLD),
        "-" * 60,
    ]
    lines.extend(details)
    lines.append("-" * 60)
    status = "PASSED" if passed else "FAILED — metric regression detected"
    lines.append(f"  Result: {status}")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_github_summary(suite: EvalSuiteResult, baseline: dict, passed: bool, details: list[str]) -> str:
    """Build a Markdown summary suitable for a GitHub PR comment."""
    status_emoji = "passed" if passed else "FAILED"
    lines = [
        f"## RAG Eval CI — {status_emoji}",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Test cases | {suite.total_cases} |",
        f"| Run ID | `{suite.run_id or 'N/A'}` |",
        f"| Threshold | {REGRESSION_THRESHOLD} |",
        "",
        "### Metric Comparison",
        "",
        "| Metric | Current | Baseline | Delta | Status |",
        "|--------|---------|----------|-------|--------|",
    ]
    for metric in METRICS:
        cur = suite.to_dict()["metrics"].get(metric, 0.0)
        base = baseline.get(metric, 0.0)
        delta = cur - base
        if delta < -REGRESSION_THRESHOLD:
            status = "FAIL"
        elif delta < 0:
            status = "WARN"
        else:
            status = "PASS"
        lines.append(f"| {metric} | {cur:.2f} | {base:.2f} | {delta:+.2f} | {status} |")

    if not passed:
        lines.extend(["", "> **Regression detected.** One or more metrics dropped beyond the threshold."])
    return "\n".join(lines)


async def main(update_baseline: bool = False) -> int:
    """Run the eval suite and return exit code (0=pass, 1=fail)."""
    # Load golden test set
    logger.info("Loading golden test set from %s", GOLDEN_PATH)
    if not GOLDEN_PATH.exists():
        logger.error(
            "Golden test set fixture missing at %s. "
            "Run with --generate-baseline after creating the fixture, "
            "or ensure tests/fixtures/golden_test_set.json exists.",
            GOLDEN_PATH,
        )
        return 1
    try:
        test_cases = load_golden_test_set(GOLDEN_PATH)
    except (FileNotFoundError, ValueError) as e:
        logger.error("Cannot load golden test set: %s", e)
        return 1

    if not test_cases:
        logger.error("Golden test set is empty — nothing to evaluate")
        return 1

    logger.info("Loaded %d test cases", len(test_cases))

    # Run eval suite
    logger.info("Starting eval suite run...")
    suite = await run_eval_suite(
        test_cases=test_cases,
        retrieval_mode="hybrid",
    )

    # Build current metrics dict
    current_metrics = {
        "faithfulness": round(suite.avg_faithfulness, 2),
        "answer_relevance": round(suite.avg_answer_relevance, 2),
        "context_precision": round(suite.avg_context_precision, 2),
        "context_recall": round(suite.avg_context_recall, 2),
        "overall": round(suite.avg_overall, 2),
    }

    # Load baseline and compare
    baseline = load_baseline()
    passed, details = compare_metrics(current_metrics, baseline)

    # Print summary
    summary = format_summary(suite, baseline, passed, details)
    print(summary)

    # Write GitHub step summary if running in Actions
    github_summary = format_github_summary(suite, baseline, passed, details)
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(github_summary + "\n")

    # Optionally update baseline
    if update_baseline:
        save_baseline(suite)

    # Save detailed results to artifacts
    results_path = FIXTURES_DIR / "eval_latest_results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(suite.to_dict(), f, indent=2)
    logger.info("Detailed results written to %s", results_path)

    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CI eval runner for RAG pipeline")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="After running eval, write current metrics as the new baseline",
    )
    parser.add_argument(
        "--generate-baseline",
        action="store_true",
        help="Run the eval suite and save results as the new baseline (alias for --update-baseline)",
    )
    args = parser.parse_args()

    should_update = args.update_baseline or args.generate_baseline
    exit_code = asyncio.run(main(update_baseline=should_update))
    sys.exit(exit_code)
