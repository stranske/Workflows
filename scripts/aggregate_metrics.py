#!/usr/bin/env python3
"""Aggregate metrics from NDJSON autopilot metrics logs.

This script analyzes LangSmith trace coverage and generates summary statistics
for monitoring observability adoption across the agent workflows.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_metrics(metrics_path: Path) -> list[dict[str, Any]]:
    """Load NDJSON metrics file."""
    metrics = []
    if not metrics_path.exists():
        return metrics

    with open(metrics_path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                metric = json.loads(line)
                metrics.append(metric)
            except json.JSONDecodeError as e:
                print(
                    f"Warning: Skipping line {line_num} (invalid JSON): {e}",
                    file=sys.stderr,
                )
    return metrics


def _metric_has_trace(metric: dict[str, Any]) -> bool:
    if metric.get("langsmith_trace_id"):
        return True
    traces = metric.get("langsmith_traces")
    return isinstance(traces, list) and any(
        isinstance(item, dict) and item.get("trace_id") for item in traces
    )


def aggregate_traces(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute trace coverage and groupings."""
    total_metrics = len(metrics)
    if total_metrics == 0:
        return {
            "total_metrics": 0,
            "total_with_traces": 0,
            "trace_coverage_pct": 0.0,
            "by_operation": {},
            "by_step": {},
        }

    # Count metrics with trace IDs
    with_traces = [m for m in metrics if _metric_has_trace(m)]
    total_with_traces = len(with_traces)
    trace_coverage_pct = (total_with_traces / total_metrics) * 100

    # Group by operation
    by_operation: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "with_trace": 0})
    for metric in metrics:
        operation = metric.get("metric_type", "unknown")
        by_operation[operation]["total"] += 1
        if _metric_has_trace(metric):
            by_operation[operation]["with_trace"] += 1

    # Calculate coverage per operation
    operation_summary = {}
    for op, counts in by_operation.items():
        coverage = (counts["with_trace"] / counts["total"]) * 100 if counts["total"] > 0 else 0.0
        operation_summary[op] = {
            "total": counts["total"],
            "with_trace": counts["with_trace"],
            "coverage_pct": round(coverage, 1),
        }

    # Group by autopilot step (if present)
    by_step: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "with_trace": 0})
    for metric in metrics:
        step = metric.get("step_name", "unknown")
        by_step[step]["total"] += 1
        if _metric_has_trace(metric):
            by_step[step]["with_trace"] += 1

    step_summary = {}
    for step, counts in by_step.items():
        coverage = (counts["with_trace"] / counts["total"]) * 100 if counts["total"] > 0 else 0.0
        step_summary[step] = {
            "total": counts["total"],
            "with_trace": counts["with_trace"],
            "coverage_pct": round(coverage, 1),
        }

    return {
        "total_metrics": total_metrics,
        "total_with_traces": total_with_traces,
        "trace_coverage_pct": round(trace_coverage_pct, 1),
        "by_operation": operation_summary,
        "by_step": step_summary,
    }


def format_report(summary: dict[str, Any]) -> str:
    """Format summary as human-readable report."""
    lines = ["# LangSmith Trace Coverage Report", ""]

    lines.append("## Overall Coverage")
    lines.append(f"- Total metrics: {summary['total_metrics']}")
    lines.append(f"- Metrics with traces: {summary['total_with_traces']}")
    lines.append(f"- Coverage: {summary['trace_coverage_pct']}%")
    lines.append("")

    if summary["by_operation"]:
        lines.append("## Coverage by Operation")
        lines.append("| Operation | Total | With Trace | Coverage |")
        lines.append("|-----------|-------|------------|----------|")
        for op, stats in sorted(summary["by_operation"].items()):
            lines.append(
                f"| {op} | {stats['total']} | {stats['with_trace']} | {stats['coverage_pct']}% |"
            )
        lines.append("")

    if summary["by_step"]:
        lines.append("## Coverage by Autopilot Step")
        lines.append("| Step | Total | With Trace | Coverage |")
        lines.append("|------|-------|------------|----------|")
        for step, stats in sorted(summary["by_step"].items()):
            lines.append(
                f"| {step} | {stats['total']} | {stats['with_trace']} | {stats['coverage_pct']}% |"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Aggregate LangSmith trace metrics from NDJSON logs"
    )
    parser.add_argument(
        "metrics_path",
        type=Path,
        nargs="?",
        help="Path to NDJSON metrics file (legacy positional form)",
    )
    parser.add_argument(
        "--metrics-file",
        type=Path,
        required=False,
        help="Path to NDJSON metrics file",
    )
    parser.add_argument(
        "--output-format",
        "--format",
        dest="output_format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Write output to file (default: stdout)",
    )

    args = parser.parse_args()
    metrics_file = args.metrics_file or args.metrics_path
    if metrics_file is None:
        parser.error("one of --metrics-file or metrics_path is required")

    # Load and aggregate metrics
    metrics = load_metrics(metrics_file)
    summary = aggregate_traces(metrics)

    # Format output
    if args.output_format == "json":
        output = json.dumps(summary, indent=2) + "\n"
    else:  # markdown
        output = format_report(summary)

    # Write output
    if args.output_file:
        args.output_file.write_text(output)
        print(f"Report written to {args.output_file}", file=sys.stderr)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
