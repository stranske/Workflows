#!/usr/bin/env python3
"""Generate feedback snippets from issue pattern corpora for prompt tuning."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_pattern_key(key: str) -> dict[str, str]:
    parts = key.split("|")
    parsed: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            continue
        label, value = part.split("=", 1)
        parsed[label.strip()] = value.strip()
    return parsed


def _format_ratio(count: int, total: int) -> str:
    if total <= 0:
        return "n/a"
    rate = (count / total) * 100
    return f"{count}/{total} ({rate:.0f}%)"


def _summarize_sections(successful: list[dict[str, Any]]) -> list[str]:
    section_counts: Counter[str] = Counter()
    total = len(successful)
    for entry in successful:
        sections = entry.get("sections")
        if not isinstance(sections, dict):
            continue
        for key, value in sections.items():
            if value:
                section_counts[key] += 1

    lines = []
    for key in ("why", "scope", "non_goals", "implementation"):
        label = key.replace("_", " ").title()
        lines.append(f"- {label}: {_format_ratio(section_counts.get(key, 0), total)}")
    return lines


def _summarize_buckets(patterns: list[dict[str, Any]], label: str) -> str:
    bucket_counts: Counter[str] = Counter()
    for pattern in patterns:
        key = str(pattern.get("pattern_key") or "")
        parsed = _parse_pattern_key(key)
        bucket = parsed.get(label)
        if bucket:
            bucket_counts[bucket] += int(pattern.get("count") or 0)
    if not bucket_counts:
        return "n/a"
    bucket, _ = bucket_counts.most_common(1)[0]
    return bucket


def build_feedback(corpus: dict[str, Any], *, max_patterns: int = 5) -> str:
    successful = corpus.get("successful_issues")
    patterns = corpus.get("patterns")

    successful_list = successful if isinstance(successful, list) else []
    patterns_list = patterns if isinstance(patterns, list) else []

    if not successful_list:
        return "\n".join(
            [
                "# Issue Formatting Feedback",
                "",
                "No successful issues available yet. Keep using the standard formatting rules.",
            ]
        )

    avg_tasks = _safe_float(
        sum(entry.get("task_count", 0) for entry in successful_list) / len(successful_list)
    )
    avg_acceptance = _safe_float(
        sum(entry.get("acceptance_count", 0) for entry in successful_list)
        / len(successful_list)
    )
    avg_tasks_text = f"{avg_tasks:.1f}" if avg_tasks is not None else "n/a"
    avg_acceptance_text = f"{avg_acceptance:.1f}" if avg_acceptance is not None else "n/a"

    task_bucket = _summarize_buckets(patterns_list, "tasks")
    acceptance_bucket = _summarize_buckets(patterns_list, "acceptance")

    lines = [
        "# Issue Formatting Feedback",
        "",
        f"Successful issue sample size: {len(successful_list)}",
        f"Typical task count: avg {avg_tasks_text} (most common bucket: {task_bucket})",
        f"Typical acceptance count: avg {avg_acceptance_text} (most common bucket: {acceptance_bucket})",
        "",
        "Common sections present:",
    ]
    lines.extend(_summarize_sections(successful_list))
    lines.append("")
    lines.append("Top patterns:")

    if patterns_list:
        for pattern in patterns_list[:max_patterns]:
            key = pattern.get("pattern_key", "unknown")
            count = pattern.get("count", 0)
            avg_task = _safe_float(pattern.get("avg_task_count"))
            avg_accept = _safe_float(pattern.get("avg_acceptance_count"))
            avg_task_text = f"{avg_task:.1f}" if avg_task is not None else "n/a"
            avg_accept_text = f"{avg_accept:.1f}" if avg_accept is not None else "n/a"
            lines.append(
                f"- {key} (count={count}, avg_tasks={avg_task_text}, avg_acceptance={avg_accept_text})"
            )
    else:
        lines.append("- n/a")

    return "\n".join(lines).strip()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate issue formatting feedback from issue pattern corpus."
    )
    parser.add_argument(
        "--corpus-path",
        default="issue-pattern-corpus.json",
        help="Path to issue pattern corpus JSON.",
    )
    parser.add_argument(
        "--output",
        default=str(Path("scripts") / "langchain" / "prompts" / "format_issue_feedback.md"),
        help="Output path for feedback snippet.",
    )
    parser.add_argument("--max-patterns", type=int, default=5, help="Max patterns to list.")
    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    corpus_path = Path(args.corpus_path)
    if not corpus_path.exists():
        print(f"issue_pattern_feedback: corpus not found: {corpus_path}", file=sys.stderr)
        return 1

    try:
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"issue_pattern_feedback: invalid JSON in {corpus_path}", file=sys.stderr)
        return 1

    if not isinstance(corpus, dict):
        print(f"issue_pattern_feedback: corpus must be a JSON object", file=sys.stderr)
        return 1

    feedback = build_feedback(corpus, max_patterns=args.max_patterns)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(feedback, encoding="utf-8")
    print(f"Wrote issue format feedback to {output_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main(sys.argv[1:]))
