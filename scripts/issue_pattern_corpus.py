#!/usr/bin/env python3
"""Build a corpus of successful issue patterns from issue and metrics logs."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.langchain import issue_formatter

SUCCESS_PLACEHOLDERS = {
    "why": "_Not provided._",
    "scope": "_Not provided._",
    "non_goals": "_Not provided._",
    "implementation": "_Not provided._",
    "tasks": "- [ ] _Not provided._",
    "acceptance": "- [ ] _Not provided._",
}

SECTION_HEADERS = {
    "why": "## Why",
    "scope": "## Scope",
    "non_goals": "## Non-Goals",
    "tasks": "## Tasks",
    "acceptance": "## Acceptance Criteria",
    "implementation": "## Implementation Notes",
}


@dataclass(frozen=True)
class CorpusCriteria:
    """Filter criteria for successful issue patterns."""

    min_completion_rate: float
    max_human_interventions: int | None
    min_tasks_total: int | None


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def _read_json_or_ndjson(path: Path) -> tuple[list[dict[str, Any]], int]:
    errors = 0
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return [], 1

    stripped = content.strip()
    if not stripped:
        return [], 0

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = None

    if parsed is not None:
        if isinstance(parsed, list):
            entries = [item for item in parsed if isinstance(item, dict)]
            errors = len(parsed) - len(entries)
            return entries, errors
        if isinstance(parsed, dict):
            return [parsed], 0
        return [], 1

    entries: list[dict[str, Any]] = []
    for line in content.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            parsed_line = json.loads(raw)
        except json.JSONDecodeError:
            errors += 1
            continue
        if isinstance(parsed_line, dict):
            entries.append(parsed_line)
        else:
            errors += 1
    return entries, errors


def _extract_pr_number(entry: dict[str, Any]) -> int | None:
    for key in ("pr_number", "pr", "pull_request_number"):
        value = _safe_int(entry.get(key))
        if value is not None:
            return value
    pull_request = entry.get("pull_request")
    if isinstance(pull_request, dict):
        return _safe_int(pull_request.get("number"))
    return None


def _index_post_merge(records: Iterable[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for record in records:
        metric_type = str(record.get("metric_type") or "").strip().lower()
        if metric_type != "post-merge":
            continue
        pr_number = _safe_int(record.get("pr_number"))
        if pr_number is None:
            continue
        existing = indexed.get(pr_number)
        if existing is None:
            indexed[pr_number] = record
            continue
        current_ts = _parse_timestamp(record.get("timestamp"))
        existing_ts = _parse_timestamp(existing.get("timestamp"))
        if existing_ts is None and current_ts is not None:
            indexed[pr_number] = record
            continue
        if current_ts is None or existing_ts is None:
            continue
        if current_ts > existing_ts:
            indexed[pr_number] = record
    return indexed


def _split_sections(formatted_body: str) -> dict[str, list[str]]:
    sections = {key: [] for key in SECTION_HEADERS}
    current: str | None = None
    for line in formatted_body.splitlines():
        heading = line.strip()
        for key, header in SECTION_HEADERS.items():
            if heading == header:
                current = key
                break
        else:
            if current:
                sections[current].append(line)
    return sections


def _section_has_content(section_key: str, lines: list[str]) -> bool:
    text = "\n".join(lines).strip()
    if not text:
        return False
    placeholder = SUCCESS_PLACEHOLDERS.get(section_key)
    return not (placeholder and text.strip() == placeholder)


def _count_checklist_items(lines: list[str]) -> int:
    count = 0
    for line in lines:
        if line.strip() == SUCCESS_PLACEHOLDERS["tasks"]:
            return 0
        if line.strip() == SUCCESS_PLACEHOLDERS["acceptance"]:
            return 0
        if line.strip().startswith("- [") and "]" in line or line.strip().startswith("- ["):
            count += 1
    return count


def _bucket_count(value: int) -> str:
    if value <= 0:
        return "0"
    if value <= 2:
        return "1-2"
    if value <= 5:
        return "3-5"
    if value <= 10:
        return "6-10"
    return "11+"


def _pattern_key(task_count: int, acceptance_count: int, flags: dict[str, bool]) -> str:
    sections = ",".join(
        key for key in ("why", "scope", "non_goals", "implementation") if flags.get(key)
    )
    if not sections:
        sections = "none"
    return (
        f"tasks={_bucket_count(task_count)}|"
        f"acceptance={_bucket_count(acceptance_count)}|"
        f"sections={sections}"
    )


def _meets_success_criteria(metrics: dict[str, Any], criteria: CorpusCriteria) -> bool:
    completion_rate = _safe_float(metrics.get("completion_rate"))
    if completion_rate is None or completion_rate < criteria.min_completion_rate:
        return False
    if criteria.max_human_interventions is not None:
        interventions = _safe_int(metrics.get("human_interventions"))
        if interventions is None or interventions > criteria.max_human_interventions:
            return False
    if criteria.min_tasks_total is not None:
        tasks_total = _safe_int(metrics.get("tasks_total"))
        if tasks_total is None or tasks_total < criteria.min_tasks_total:
            return False
    return True


def _build_issue_pattern(
    issue: dict[str, Any], metrics: dict[str, Any], include_formatted: bool
) -> dict[str, Any]:
    title = str(issue.get("title") or issue.get("issue_title") or "").strip()
    body = str(issue.get("body") or issue.get("issue_body") or "").strip()
    formatted = issue_formatter.format_issue_body(body, use_llm=False)["formatted_body"]
    sections = _split_sections(formatted)
    flags = {key: _section_has_content(key, sections[key]) for key in SECTION_HEADERS}
    task_count = _count_checklist_items(sections["tasks"])
    acceptance_count = _count_checklist_items(sections["acceptance"])

    pattern = {
        "issue_number": issue.get("issue_number") or issue.get("number"),
        "pr_number": _extract_pr_number(issue),
        "title": title,
        "task_count": task_count,
        "acceptance_count": acceptance_count,
        "sections": {key: flags[key] for key in ("why", "scope", "non_goals", "implementation")},
        "completion_rate": metrics.get("completion_rate"),
        "iteration_count": metrics.get("iteration_count"),
        "human_interventions": metrics.get("human_interventions"),
        "pattern_key": _pattern_key(task_count, acceptance_count, flags),
    }
    if include_formatted:
        pattern["formatted_body"] = formatted
    return pattern


def build_corpus(
    issues: Iterable[dict[str, Any]],
    metrics: Iterable[dict[str, Any]],
    criteria: CorpusCriteria,
    *,
    include_formatted: bool = False,
) -> dict[str, Any]:
    metrics_index = _index_post_merge(metrics)
    successful: list[dict[str, Any]] = []

    for issue in issues:
        pr_number = _extract_pr_number(issue)
        if pr_number is None:
            continue
        metric = metrics_index.get(pr_number)
        if not metric or not _meets_success_criteria(metric, criteria):
            continue
        successful.append(_build_issue_pattern(issue, metric, include_formatted))

    pattern_index: dict[str, dict[str, Any]] = {}
    for entry in successful:
        key = entry["pattern_key"]
        grouped = pattern_index.setdefault(
            key,
            {
                "pattern_key": key,
                "count": 0,
                "issue_numbers": [],
                "avg_task_count": 0.0,
                "avg_acceptance_count": 0.0,
            },
        )
        grouped["count"] += 1
        if entry.get("issue_number") is not None:
            grouped["issue_numbers"].append(entry["issue_number"])
        grouped["avg_task_count"] += entry["task_count"]
        grouped["avg_acceptance_count"] += entry["acceptance_count"]

    patterns = []
    for grouped in pattern_index.values():
        count = grouped["count"]
        grouped["avg_task_count"] = grouped["avg_task_count"] / count
        grouped["avg_acceptance_count"] = grouped["avg_acceptance_count"] / count
        patterns.append(grouped)

    patterns.sort(key=lambda item: item["count"], reverse=True)
    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "criteria": {
            "min_completion_rate": criteria.min_completion_rate,
            "max_human_interventions": criteria.max_human_interventions,
            "min_tasks_total": criteria.min_tasks_total,
        },
        "successful_issues": successful,
        "patterns": patterns,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build corpus of successful issue patterns.")
    parser.add_argument("--issues-path", required=True, help="Path to issue JSON/NDJSON.")
    parser.add_argument("--metrics-path", required=True, help="Path to metrics NDJSON.")
    parser.add_argument(
        "--output",
        default="issue-pattern-corpus.json",
        help="Output JSON path",
    )
    parser.add_argument(
        "--min-completion-rate",
        type=float,
        default=1.0,
        help="Minimum completion_rate to treat as successful.",
    )
    parser.add_argument(
        "--max-human-interventions",
        type=int,
        default=None,
        help="Max allowed human_interventions to include (omit to disable filter).",
    )
    parser.add_argument(
        "--min-tasks-total",
        type=int,
        default=None,
        help="Minimum tasks_total to include (omit to disable filter).",
    )
    parser.add_argument(
        "--include-formatted-body",
        action="store_true",
        help="Include formatted issue body in output.",
    )
    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    issues_path = Path(args.issues_path)
    metrics_path = Path(args.metrics_path)

    issue_entries, issue_errors = _read_json_or_ndjson(issues_path)
    metric_entries, metric_errors = _read_json_or_ndjson(metrics_path)

    criteria = CorpusCriteria(
        min_completion_rate=args.min_completion_rate,
        max_human_interventions=args.max_human_interventions,
        min_tasks_total=args.min_tasks_total,
    )

    corpus = build_corpus(
        issue_entries,
        metric_entries,
        criteria,
        include_formatted=args.include_formatted_body,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(corpus, indent=2, ensure_ascii=True), encoding="utf-8")

    if issue_errors or metric_errors:
        print(
            f"issue_pattern_corpus: parse errors (issues={issue_errors}, metrics={metric_errors})",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main(sys.argv[1:]))
