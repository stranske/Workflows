#!/usr/bin/env python3
"""Generate a markdown report from issue pattern corpora."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.metrics_format_utils import format_percentage, truncate_string


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_float(value: Any, default: str = "n/a") -> str:
    parsed = _safe_float(value)
    return f"{parsed:.1f}" if parsed is not None else default


def _format_completion(value: Any) -> str:
    parsed = _safe_float(value)
    if parsed is None:
        return "n/a"
    return format_percentage(parsed * 100, decimals=1)


def build_report(corpus: dict[str, Any], *, max_patterns: int = 10, max_issues: int = 10) -> str:
    generated_at = corpus.get("generated_at") or "n/a"
    criteria = corpus.get("criteria") if isinstance(corpus.get("criteria"), dict) else {}
    patterns = corpus.get("patterns") if isinstance(corpus.get("patterns"), list) else []
    issues = (
        corpus.get("successful_issues") if isinstance(corpus.get("successful_issues"), list) else []
    )

    lines = [
        "# Issue Pattern Report",
        "",
        f"Generated at: {generated_at}",
        f"Successful issues: {len(issues)}",
        f"Distinct patterns: {len(patterns)}",
        "",
        "## Criteria",
        f"- min_completion_rate: {criteria.get('min_completion_rate', 'n/a')}",
        f"- max_human_interventions: {criteria.get('max_human_interventions', 'n/a')}",
        f"- min_tasks_total: {criteria.get('min_tasks_total', 'n/a')}",
        "",
    ]

    lines.extend(
        [
            "## Patterns",
            "",
            "| Pattern | Count | Avg tasks | Avg acceptance | Issues |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if patterns:
        for pattern in patterns[:max_patterns]:
            issue_numbers = pattern.get("issue_numbers")
            if isinstance(issue_numbers, list) and issue_numbers:
                issue_list = ", ".join(str(value) for value in issue_numbers[:5])
            else:
                issue_list = "n/a"
            lines.append(
                "| {pattern} | {count} | {avg_tasks} | {avg_acceptance} | {issues} |".format(
                    pattern=pattern.get("pattern_key", "n/a"),
                    count=pattern.get("count", 0),
                    avg_tasks=_format_float(pattern.get("avg_task_count")),
                    avg_acceptance=_format_float(pattern.get("avg_acceptance_count")),
                    issues=issue_list,
                )
            )
    else:
        lines.append("| n/a | 0 | n/a | n/a | n/a |")

    lines.extend(["", "## Successful Issues (sample)", ""])
    lines.extend(
        [
            "| PR | Issue | Title | Completion | Iterations | Interventions | Tasks | Acceptance |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if issues:
        for issue in issues[:max_issues]:
            lines.append(
                "| {pr} | {issue} | {title} | {completion} | {iterations} | {interventions} | {tasks} | {acceptance} |".format(
                    pr=issue.get("pr_number", "n/a"),
                    issue=issue.get("issue_number", "n/a"),
                    title=truncate_string(str(issue.get("title") or "n/a"), max_length=40),
                    completion=_format_completion(issue.get("completion_rate")),
                    iterations=issue.get("iteration_count", "n/a"),
                    interventions=issue.get("human_interventions", "n/a"),
                    tasks=issue.get("task_count", "n/a"),
                    acceptance=issue.get("acceptance_count", "n/a"),
                )
            )
    else:
        lines.append("| n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")

    return "\n".join(lines).strip()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate issue pattern report from issue pattern corpus."
    )
    parser.add_argument(
        "--corpus-path",
        default="issue-pattern-corpus.json",
        help="Path to issue pattern corpus JSON.",
    )
    parser.add_argument(
        "--output",
        default="issue-pattern-report.md",
        help="Output markdown path.",
    )
    parser.add_argument("--max-patterns", type=int, default=10, help="Max patterns to list.")
    parser.add_argument("--max-issues", type=int, default=10, help="Max issues to list.")
    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    corpus_path = Path(args.corpus_path)
    if not corpus_path.exists():
        print(f"issue_pattern_report: corpus not found: {corpus_path}", file=sys.stderr)
        return 1

    try:
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"issue_pattern_report: invalid JSON in {corpus_path}", file=sys.stderr)
        return 1

    if not isinstance(corpus, dict):
        print("issue_pattern_report: corpus must be a JSON object", file=sys.stderr)
        return 1

    report = build_report(corpus, max_patterns=args.max_patterns, max_issues=args.max_issues)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"Wrote issue pattern report to {output_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main(sys.argv[1:]))
