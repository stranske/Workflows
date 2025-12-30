#!/usr/bin/env python3
"""Generate coverage trend analysis from coverage outputs.

This script compares current coverage against a baseline and generates trend
artifacts for CI reporting, including low-coverage hotspot files.
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
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        return {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _extract_coverage_percent(coverage_json: dict[str, Any]) -> float:
    """Extract overall coverage percentage from coverage.json."""
    totals = coverage_json.get("totals", {})
    return float(totals.get("percent_covered", 0.0))


def _get_hotspots(
    coverage_json: dict[str, Any],
    limit: int = 15,
    low_threshold: float = 50.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract hotspot files from coverage.json.

    Returns:
        Tuple of (all_hotspots sorted by coverage, low_coverage_files below threshold)
    """
    files = coverage_json.get("files", {})
    all_files = []

    for filepath, data in files.items():
        summary = data.get("summary", {})
        percent = summary.get("percent_covered", 0.0)
        missing = summary.get("missing_lines", 0)
        covered = summary.get("covered_lines", 0)
        all_files.append(
            {
                "file": filepath,
                "coverage": percent,
                "missing_lines": missing,
                "covered_lines": covered,
            }
        )

    # Sort by coverage ascending (lowest first)
    all_files.sort(key=lambda x: x["coverage"])

    # Split into hotspots and low coverage
    hotspots = all_files[:limit]
    low_coverage = [f for f in all_files if f["coverage"] < low_threshold][:limit]

    return hotspots, low_coverage


def _format_hotspot_table(files: list[dict[str, Any]], title: str) -> str:
    """Format a markdown table of hotspot files."""
    if not files:
        return ""

    lines = [
        f"### {title}",
        "",
        "| File | Coverage | Missing |",
        "|------|----------|---------|",
    ]

    for f in files:
        lines.append(f"| `{f['file']}` | {f['coverage']:.1f}% | {f['missing_lines']} |")

    lines.append("")
    return "\n".join(lines)


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
    parser.add_argument("--hotspot-limit", type=int, default=15, help="Max hotspot files to show")
    parser.add_argument("--low-threshold", type=float, default=50.0, help="Low coverage threshold")
    parser.add_argument(
        "--soft", action="store_true", help="Soft gate mode - report only, always exit 0"
    )
    parsed = parser.parse_args(args)

    # Load current coverage
    coverage_data = {}
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

    # Get hotspots
    hotspots, low_coverage = _get_hotspots(
        coverage_data,
        limit=parsed.hotspot_limit,
        low_threshold=parsed.low_threshold,
    )

    # Generate trend record
    trend_record = {
        "current": current_coverage,
        "baseline": baseline_coverage,
        "delta": delta,
        "minimum": parsed.minimum,
        "passes_minimum": passes_minimum,
        "hotspot_count": len(hotspots),
        "low_coverage_count": len(low_coverage),
    }

    # Write outputs
    if parsed.artifact_path:
        parsed.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        # Include hotspots in artifact for downstream processing
        artifact_data = {
            **trend_record,
            "hotspots": hotspots,
            "low_coverage_files": low_coverage,
        }
        parsed.artifact_path.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")

    status = "✅ Pass" if passes_minimum else "❌ Below minimum"
    summary = f"""## Coverage Trend

| Metric | Value |
|--------|-------|
| Current | {current_coverage:.2f}% |
| Baseline | {baseline_coverage:.2f}% |
| Delta | {delta:+.2f}% |
| Minimum | {parsed.minimum:.2f}% |
| Status | {status} |

"""

    # Add hotspot tables if we have coverage data
    if hotspots:
        summary += _format_hotspot_table(hotspots, "Top Coverage Hotspots (lowest coverage)")

    if low_coverage:
        summary += _format_hotspot_table(
            low_coverage,
            f"Low Coverage Files (<{parsed.low_threshold}%)",
        )

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
            f.write(f"hotspot_count={len(hotspots)}\n")
            f.write(f"low_coverage_count={len(low_coverage)}\n")

    print(
        f"Coverage: {current_coverage:.2f}% "
        f"(baseline: {baseline_coverage:.2f}%, delta: {delta:+.2f}%)"
    )
    if hotspots:
        print(f"Hotspots: {len(hotspots)} files with lowest coverage")

    # In soft mode, always return 0 (report only, don't fail build)
    if parsed.soft:
        return 0
    return 0 if passes_minimum else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
