#!/usr/bin/env python3
"""Generate coverage trend analysis from coverage outputs.

This script compares current coverage against a baseline and generates trend
artifacts for CI reporting.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    """Load JSON from a file, returning empty dict on error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _extract_coverage_percent(coverage_json: dict[str, Any]) -> float:
    """Extract overall coverage percentage from coverage.json."""
    totals = coverage_json.get("totals", {})
    return float(totals.get("percent_covered", 0.0))


def main(args: list[str] | None = None) -> int:
    """Main entry point for coverage trend analysis."""
    parser = argparse.ArgumentParser(description="Coverage trend analysis")
    parser.add_argument("--coverage-xml", type=Path, help="Path to coverage.xml")
    parser.add_argument("--coverage-json", type=Path, help="Path to coverage.json")
    parser.add_argument("--baseline", type=Path, help="Path to baseline JSON")
    parser.add_argument("--summary-path", type=Path, help="Path to output summary markdown")
    parser.add_argument("--job-summary", type=Path, help="Path to GITHUB_STEP_SUMMARY")
    parser.add_argument("--artifact-path", type=Path, help="Path to output trend artifact")
    parser.add_argument("--github-output", type=Path, help="Path to write env file")
    parser.add_argument("--minimum", type=float, default=70.0, help="Minimum coverage threshold")
    parsed = parser.parse_args(args)

    # Load current coverage
    current_coverage = 0.0
    if parsed.coverage_json and parsed.coverage_json.exists():
        coverage_data = _load_json(parsed.coverage_json)
        current_coverage = _extract_coverage_percent(coverage_data)

    # Load baseline
    baseline_coverage = 0.0
    if parsed.baseline and parsed.baseline.exists():
        baseline_data = _load_json(parsed.baseline)
        baseline_coverage = float(baseline_data.get("coverage", 0.0))

    # Calculate delta
    delta = current_coverage - baseline_coverage
    passes_minimum = current_coverage >= parsed.minimum

    # Generate trend record
    trend_record = {
        "current": current_coverage,
        "baseline": baseline_coverage,
        "delta": delta,
        "minimum": parsed.minimum,
        "passes_minimum": passes_minimum,
    }

    # Write outputs
    if parsed.artifact_path:
        parsed.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        parsed.artifact_path.write_text(json.dumps(trend_record, indent=2), encoding="utf-8")

    summary = f"""## Coverage Trend

| Metric | Value |
|--------|-------|
| Current | {current_coverage:.2f}% |
| Baseline | {baseline_coverage:.2f}% |
| Delta | {delta:+.2f}% |
| Minimum | {parsed.minimum:.2f}% |
| Status | {"✅ Pass" if passes_minimum else "❌ Below minimum"} |
"""

    if parsed.summary_path:
        parsed.summary_path.parent.mkdir(parents=True, exist_ok=True)
        parsed.summary_path.write_text(summary, encoding="utf-8")

    if parsed.job_summary and parsed.job_summary.exists():
        with parsed.job_summary.open("a", encoding="utf-8") as f:
            f.write(summary)

    if parsed.github_output:
        parsed.github_output.parent.mkdir(parents=True, exist_ok=True)
        with parsed.github_output.open("w", encoding="utf-8") as f:
            f.write(f"coverage={current_coverage:.2f}\n")
            f.write(f"baseline={baseline_coverage:.2f}\n")
            f.write(f"delta={delta:.2f}\n")
            f.write(f"passes_minimum={'true' if passes_minimum else 'false'}\n")

    print(
        f"Coverage: {current_coverage:.2f}% (baseline: {baseline_coverage:.2f}%, delta: {delta:+.2f}%)"
    )
    return 0 if passes_minimum else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
