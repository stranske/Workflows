#!/usr/bin/env python3
"""Check workflow health metrics and report status.

This script analyzes workflow run metrics to identify patterns
that may indicate issues needing attention.
"""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


def load_workflow_runs(metrics_path: str) -> list[dict]:
    """Load workflow run metrics from NDJSON file."""
    runs: list[dict] = []
    path = Path(metrics_path)
    if not path.exists():
        return runs

    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                runs.append(json.loads(line))
    return runs


def calculate_success_rate(runs: list[dict]) -> float:
    """Calculate success rate from workflow runs."""
    if not runs:
        return 0.0

    successes = sum(1 for r in runs if r.get("verdict") == "pass" or r.get("status") == "success")
    return successes / len(runs) * 100


def analyze_failure_patterns(runs: list[dict]) -> dict[str, int]:
    """Analyze runs to identify common failure patterns."""
    failures = [r for r in runs if r.get("verdict") == "fail" or r.get("status") == "failure"]

    patterns: dict[str, int] = {}
    for failure in failures:
        reason = failure.get("skip_reason") or failure.get("error") or "unknown"
        if reason in patterns:
            patterns[reason] += 1
        else:
            patterns[reason] = 1

    return patterns


def get_recent_runs(runs: list[dict], days: int = 7) -> list[dict]:
    """Filter runs to only those within the last N days."""
    cutoff = datetime.now(UTC).timestamp() - (days * 86400)

    recent: list[dict] = []
    for run in runs:
        recorded = run.get("recorded_at", "")
        if recorded:
            try:
                dt = datetime.fromisoformat(recorded.replace("Z", "+00:00"))
                if dt.timestamp() >= cutoff:
                    recent.append(run)
            except ValueError:
                # Ignore runs with invalid or unparsable timestamps when filtering by recency.
                pass
    return recent


def format_duration(seconds: int) -> str:
    """Format duration in human readable form."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m"


def generate_report(metrics_path: str, output_path: str | None = None) -> dict:
    """Generate a health report from workflow metrics."""
    runs = load_workflow_runs(metrics_path)
    recent = get_recent_runs(runs)

    report = {
        "total_runs": len(runs),
        "recent_runs": len(recent),
        "overall_success_rate": calculate_success_rate(runs),
        "recent_success_rate": calculate_success_rate(recent),
        "failure_patterns": analyze_failure_patterns(runs),
        "generated_at": datetime.now(UTC).isoformat(),
    }

    if output_path:
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

    return report


def main() -> None:
    """Main entry point."""
    metrics_path = os.environ.get("METRICS_PATH", "workflow-metrics.ndjson")
    output_path = os.environ.get("OUTPUT_PATH")

    report = generate_report(metrics_path, output_path)

    print("Workflow Health Report")
    print("=" * 40)
    print(f"Total runs analyzed: {report['total_runs']}")
    print(f"Recent runs (7 days): {report['recent_runs']}")
    print(f"Overall success rate: {report['overall_success_rate']:.1f}%")
    print(f"Recent success rate: {report['recent_success_rate']:.1f}%")

    if report["failure_patterns"]:
        print("\nFailure patterns:")
        for pattern, count in report["failure_patterns"].items():
            print(f"  - {pattern}: {count}")

    # Exit with error if recent success rate is below threshold
    threshold = float(os.environ.get("SUCCESS_THRESHOLD", "80"))
    if report["recent_success_rate"] < threshold:
        print(f"\n⚠️ Warning: Recent success rate below {threshold}% threshold")
        sys.exit(1)


if __name__ == "__main__":
    main()
