#!/usr/bin/env python3
"""Coverage guard script for maintaining baseline breach issues.

This script compares current coverage against a baseline and creates/updates
a tracking issue when coverage falls below the threshold.
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


def _get_hotspots(coverage_data: dict[str, Any], limit: int = 15) -> list[dict[str, Any]]:
    """Extract files with lowest coverage from coverage.json."""
    files = coverage_data.get("files", {})
    hotspots = []

    for filepath, data in files.items():
        summary = data.get("summary", {})
        percent = summary.get("percent_covered", 0.0)
        missing = summary.get("missing_lines", 0)
        hotspots.append(
            {
                "file": filepath,
                "coverage": percent,
                "missing_lines": missing,
            }
        )

    # Sort by coverage ascending (lowest first)
    hotspots.sort(key=lambda x: x["coverage"])
    return hotspots[:limit]


def _format_issue_body(
    current: float,
    baseline: float,
    delta: float,
    hotspots: list[dict[str, Any]],
    run_url: str,
) -> str:
    """Format the issue body with coverage summary and hotspots."""
    status_emoji = "✅" if current >= baseline else "❌"

    body = f"""## Coverage Baseline Breach Report

{status_emoji} **Current Coverage: {current:.2f}%** (baseline: {baseline:.2f}%, delta: {delta:+.2f}%)

### Summary

| Metric | Value |
|--------|-------|
| Current | {current:.2f}% |
| Baseline | {baseline:.2f}% |
| Delta | {delta:+.2f}% |
| Status | {"Pass ✅" if current >= baseline else "Below baseline ❌"} |

### Low Coverage Hotspots

These files have the lowest coverage and are candidates for additional tests:

| File | Coverage | Missing Lines |
|------|----------|---------------|
"""

    for spot in hotspots:
        body += f"| `{spot['file']}` | {spot['coverage']:.1f}% | {spot['missing_lines']} |\n"

    if not hotspots:
        body += "| _(no files with low coverage)_ | - | - |\n"

    body += f"""

### Actions

- [ ] Review hotspot files and add tests for uncovered code
- [ ] Update baseline once coverage improves

### Source

[Gate Workflow Run]({run_url})

---
_This issue is automatically updated by the coverage guard workflow._
"""
    return body


def _find_or_create_issue(repo: str, title: str, body: str, labels: list[str]) -> None:
    """Find existing issue or create a new one using gh CLI."""
    import subprocess

    # Search for existing issue
    search_result = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--search",
            f'"{title}" in:title',
            "--json",
            "number,title",
            "--limit",
            "1",
        ],
        capture_output=True,
        text=True,
    )

    existing_issues = json.loads(search_result.stdout) if search_result.stdout.strip() else []

    if existing_issues:
        # Update existing issue
        issue_number = existing_issues[0]["number"]
        subprocess.run(
            ["gh", "issue", "edit", str(issue_number), "--repo", repo, "--body", body],
            check=True,
        )
        print(f"Updated issue #{issue_number}")
    else:
        # Create new issue
        label_args = []
        for label in labels:
            label_args.extend(["--label", label])

        subprocess.run(
            [
                "gh",
                "issue",
                "create",
                "--repo",
                repo,
                "--title",
                title,
                "--body",
                body,
                *label_args,
            ],
            check=True,
        )
        print(f"Created new issue: {title}")


def main(args: list[str] | None = None) -> int:
    """Main entry point for coverage guard."""
    parser = argparse.ArgumentParser(description="Coverage guard - maintain baseline breach issues")
    parser.add_argument("--repo", required=True, help="Repository (owner/repo)")
    parser.add_argument("--trend-path", type=Path, help="Path to coverage-trend.json")
    parser.add_argument("--coverage-path", type=Path, help="Path to coverage.json")
    parser.add_argument("--baseline-path", type=Path, help="Path to coverage-baseline.json")
    parser.add_argument("--run-url", default="", help="URL to the workflow run")
    parser.add_argument("--issue-title", default="[coverage] baseline breach", help="Issue title")
    parser.add_argument("--dry-run", action="store_true", help="Print issue body without creating")
    parsed = parser.parse_args(args)

    # Load trend data
    trend_data = {}
    if parsed.trend_path and parsed.trend_path.exists():
        trend_data = _load_json(parsed.trend_path)

    # Load coverage data for hotspots
    coverage_data = {}
    if parsed.coverage_path and parsed.coverage_path.exists():
        coverage_data = _load_json(parsed.coverage_path)

    # Load baseline
    baseline_data = {}
    if parsed.baseline_path and parsed.baseline_path.exists():
        baseline_data = _load_json(parsed.baseline_path)

    # Extract values
    current = trend_data.get("current", 0.0)
    baseline = baseline_data.get("coverage", trend_data.get("baseline", 70.0))
    delta = current - baseline

    # Get hotspots
    hotspots = _get_hotspots(coverage_data)

    # Format issue body
    body = _format_issue_body(current, baseline, delta, hotspots, parsed.run_url)

    if parsed.dry_run:
        print("=" * 60)
        print(f"Issue Title: {parsed.issue_title}")
        print("=" * 60)
        print(body)
        return 0

    # Create or update issue
    if current < baseline:
        _find_or_create_issue(
            repo=parsed.repo,
            title=parsed.issue_title,
            body=body,
            labels=["coverage", "automated"],
        )
    else:
        print(f"Coverage {current:.2f}% meets baseline {baseline:.2f}% - no issue needed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
