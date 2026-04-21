#!/usr/bin/env python3
"""Coverage guard script for maintaining baseline breach issues.

This script compares current coverage against a baseline and creates/updates
a tracking issue when coverage falls below the threshold.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_TREND_PATH = Path("coverage-trend.json")
DEFAULT_COVERAGE_PATH = Path("coverage.json")
DEFAULT_BASELINE_PATH = Path("config/coverage-baseline.json")


def _load_json(path: Path) -> dict[str, Any]:
    """Load JSON from a file, returning empty dict on error."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _to_float(value: Any, default: float = 0.0) -> float:
    """Return a finite float for numeric-ish values."""
    parsed = _parse_finite_float(value)
    return parsed if parsed is not None else default


def _parse_finite_float(value: Any) -> float | None:
    """Parse a finite float or return None for missing/invalid values."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
    elif isinstance(value, str):
        try:
            parsed = float(value)
        except (OverflowError, ValueError):
            return None
    else:
        return None
    return parsed if math.isfinite(parsed) else None


def _to_int(value: Any, default: int = 0) -> int:
    """Return an integer for numeric-ish values."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return default
        return int(value)
    if isinstance(value, str):
        try:
            parsed = float(value)
            if not math.isfinite(parsed):
                return default
            return int(parsed)
        except (OverflowError, ValueError):
            return default
    return default


def _get_hotspots(coverage_data: dict[str, Any], limit: int = 15) -> list[dict[str, Any]]:
    """Extract files with lowest coverage from coverage.json."""
    files = coverage_data.get("files", {})
    if not isinstance(files, dict):
        return []
    hotspots = []

    for filepath, data in files.items():
        if not isinstance(data, dict):
            continue
        summary = data.get("summary", {})
        if not isinstance(summary, dict):
            continue
        percent = _parse_finite_float(summary.get("percent_covered"))
        if percent is None:
            continue
        missing = _to_int(summary.get("missing_lines"))
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

    source_section = (
        f"\n### Source\n\n[Gate Workflow Run]({run_url})\n" if run_url else "\n### Source\n\nRun URL unavailable.\n"
    )

    body += f"""

### Actions

- [ ] Review hotspot files and add tests for uncovered code
- [ ] Update baseline once coverage improves
{source_section}

---
_This issue is automatically updated by the coverage guard workflow._
"""
    return body


def _format_recovery_body(current: float, baseline: float, delta: float, run_url: str) -> str:
    """Format a concise recovery comment for closing a breach issue."""
    source_line = f"\n\n[Gate Workflow Run]({run_url})" if run_url else ""
    return f"""Coverage has recovered above the configured baseline.

| Metric | Value |
|--------|-------|
| Current | {current:.2f}% |
| Baseline | {baseline:.2f}% |
| Delta | {delta:+.2f}% |

Closing the coverage baseline breach issue.{source_line}
"""


def _find_existing_issue(repo: str, title: str) -> dict[str, Any] | None:
    """Find an existing issue by title using gh CLI."""
    search_query = f"{title.replace(chr(34), ' ')} in:title"
    for state in ("open", "all"):
        search_result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                repo,
                "--state",
                state,
                "--search",
                search_query,
                "--json",
                "number,title,state",
                "--limit",
                "1",
            ],
            capture_output=True,
            text=True,
        )

        if search_result.returncode != 0:
            error_message = search_result.stderr.strip() or "unknown gh error"
            print(f"Failed to search for existing issues: {error_message}", file=sys.stderr)
            raise RuntimeError("gh issue list failed")

        try:
            existing_issues = json.loads(search_result.stdout) if search_result.stdout.strip() else []
        except json.JSONDecodeError as exc:
            print("Failed to parse gh issue list output as JSON.", file=sys.stderr)
            if search_result.stderr.strip():
                print(search_result.stderr.strip(), file=sys.stderr)
            raise RuntimeError("gh issue list returned invalid JSON") from exc

        if existing_issues:
            return existing_issues[0]

    return None


def _find_or_create_issue(repo: str, title: str, body: str, labels: list[str]) -> None:
    """Find existing issue or create a new one using gh CLI."""
    existing_issue = _find_existing_issue(repo, title)

    if existing_issue:
        issue_number = existing_issue["number"]
        if str(existing_issue.get("state", "")).upper() == "CLOSED":
            subprocess.run(
                ["gh", "issue", "reopen", str(issue_number), "--repo", repo],
                check=True,
            )
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


def _close_existing_issue(repo: str, title: str, body: str) -> None:
    """Close the existing baseline breach issue after coverage recovers."""
    existing_issue = _find_existing_issue(repo, title)
    if not existing_issue:
        print("Coverage recovered; no existing breach issue found")
        return

    issue_number = existing_issue["number"]
    if str(existing_issue.get("state", "")).upper() == "CLOSED":
        print(f"Coverage recovered; issue #{issue_number} is already closed")
        return

    subprocess.run(
        ["gh", "issue", "comment", str(issue_number), "--repo", repo, "--body", body],
        check=True,
    )
    subprocess.run(
        [
            "gh",
            "issue",
            "close",
            str(issue_number),
            "--repo",
            repo,
            "--reason",
            "completed",
        ],
        check=True,
    )
    print(f"Closed recovered issue #{issue_number}")


def _recovery_window_satisfied(
    trend_data: dict[str, Any], baseline: float, recovery_window: int
) -> bool:
    """Return whether recent coverage samples satisfy the configured recovery window."""
    if recovery_window <= 1:
        return True
    history = trend_data.get("history")
    if not isinstance(history, list) or len(history) < recovery_window:
        return False
    recent = history[-recovery_window:]
    for record in recent:
        if not isinstance(record, dict):
            return False
        current = _parse_finite_float(record.get("current"))
        if current is None or current < baseline:
            return False
    return True


def main(args: list[str] | None = None) -> int:
    """Main entry point for coverage guard."""
    parser = argparse.ArgumentParser(description="Coverage guard - maintain baseline breach issues")
    parser.add_argument("--repo", required=True, help="Repository (owner/repo)")
    parser.add_argument(
        "--trend-path",
        type=Path,
        default=DEFAULT_TREND_PATH,
        help="Path to coverage-trend.json",
    )
    parser.add_argument(
        "--coverage-path",
        type=Path,
        default=DEFAULT_COVERAGE_PATH,
        help="Path to coverage.json",
    )
    parser.add_argument(
        "--baseline-path",
        type=Path,
        default=DEFAULT_BASELINE_PATH,
        help="Path to coverage-baseline.json",
    )
    parser.add_argument("--run-url", default="", help="URL to the workflow run")
    parser.add_argument("--issue-title", default="[coverage] baseline breach", help="Issue title")
    parser.add_argument(
        "--recovery-window",
        type=int,
        default=None,
        help="Number of consecutive recovered samples required before closing",
    )
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

    if not trend_data:
        print("No coverage trend payload found; skipping coverage guard update")
        return 0

    # Extract values
    current = _parse_finite_float(trend_data.get("current"))
    if current is None:
        print("Coverage trend payload has no finite current value; skipping coverage guard update")
        return 0
    baseline = _to_float(
        baseline_data.get("line", baseline_data.get("coverage")),
        _to_float(trend_data.get("baseline"), 70.0),
    )
    delta = current - baseline
    configured_recovery_window = _to_int(
        parsed.recovery_window
        if parsed.recovery_window is not None
        else baseline_data.get("recovery_window", baseline_data.get("recovery_runs")),
        1,
    )

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
        try:
            _find_or_create_issue(
                repo=parsed.repo,
                title=parsed.issue_title,
                body=body,
                labels=["coverage", "automated"],
            )
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            print(f"Failed to create or update coverage issue: {exc}", file=sys.stderr)
            return 1
    else:
        print(f"Coverage {current:.2f}% meets baseline {baseline:.2f}% - no open issue needed")
        if not _recovery_window_satisfied(trend_data, baseline, configured_recovery_window):
            print(
                "Coverage recovered, but configured recovery window is not satisfied; "
                "leaving any breach issue open"
            )
            return 0
        try:
            _close_existing_issue(
                parsed.repo,
                parsed.issue_title,
                _format_recovery_body(current, baseline, delta, parsed.run_url),
            )
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            print(f"Failed to close recovered coverage issue: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
