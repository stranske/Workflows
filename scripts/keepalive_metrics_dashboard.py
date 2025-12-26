#!/usr/bin/env python3
"""Generate a keepalive metrics dashboard from an NDJSON log."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _read_ndjson(path: Path) -> tuple[list[dict[str, Any]], int]:
    entries: list[dict[str, Any]] = []
    errors = 0
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return entries, 1
    for line in content.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            errors += 1
            continue
        if isinstance(parsed, dict):
            entries.append(parsed)
        else:
            errors += 1
    return entries, errors


def _format_counter(counter: Counter[str]) -> str:
    if not counter:
        return "n/a"
    return ", ".join(f"{key} ({count})" for key, count in counter.most_common())


def _format_rate(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "n/a"
    rate = (numerator / denominator) * 100
    return f"{rate:.1f}% ({numerator}/{denominator})"


def _summarise(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    successes = 0
    error_breakdown: Counter[str] = Counter()
    iteration_counts: Counter[str] = Counter()
    pr_iterations: dict[int, int] = {}

    for record in records:
        total += 1
        error_category_raw = record.get("error_category")
        error_category = str(error_category_raw).strip() if error_category_raw is not None else ""
        if not error_category:
            error_category = "unknown"
        if error_category.lower() == "none":
            successes += 1
        error_breakdown[error_category] += 1

        iteration = _safe_int(record.get("iteration"))
        if iteration is not None:
            iteration_counts[str(iteration)] += 1

        pr_number = _safe_int(record.get("pr_number"))
        if pr_number is not None and iteration is not None:
            pr_iterations[pr_number] = max(iteration, pr_iterations.get(pr_number, 0))

    avg_iterations = None
    if pr_iterations:
        avg_iterations = sum(pr_iterations.values()) / len(pr_iterations)

    return {
        "total": total,
        "successes": successes,
        "error_breakdown": error_breakdown,
        "iteration_counts": iteration_counts,
        "avg_iterations": avg_iterations,
    }


def build_dashboard(records: list[dict[str, Any]], errors: int) -> str:
    summary = _summarise(records)
    avg_iterations = summary["avg_iterations"]
    avg_iterations_text = "n/a" if avg_iterations is None else f"{avg_iterations:.1f}"

    lines = [
        "# Keepalive Metrics Dashboard",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Total records | {summary['total']} |",
        f"| Success rate | {_format_rate(summary['successes'], summary['total'])} |",
        f"| Avg iterations per PR | {avg_iterations_text} |",
        f"| Iteration distribution | {_format_counter(summary['iteration_counts'])} |",
        f"| Error breakdown | {_format_counter(summary['error_breakdown'])} |",
        f"| Parse errors | {errors} |",
        "",
    ]
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build keepalive metrics dashboard from NDJSON logs.")
    parser.add_argument("--path", default="keepalive-metrics.ndjson", help="NDJSON log path")
    parser.add_argument(
        "--output", default="keepalive-metrics-dashboard.md", help="Markdown output path"
    )
    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    path = Path(args.path)
    if not path.exists():
        print(f"keepalive_metrics_dashboard: log not found: {path}", file=sys.stderr)
        return 1

    records, errors = _read_ndjson(path)
    dashboard = build_dashboard(records, errors)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(dashboard, encoding="utf-8")
    print(f"Wrote keepalive metrics dashboard to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
