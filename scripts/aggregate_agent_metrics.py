#!/usr/bin/env python3
"""Aggregate agent workflow metrics from NDJSON artifacts.

The script scans a directory for metrics artifacts produced by the
keepalive, autofix, and verifier workflows, then emits a markdown summary
with high-level statistics and completion rates.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import statistics
from pathlib import Path
from typing import List, Mapping, MutableMapping, Sequence, Tuple


def to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def load_records(artifacts_dir: Path) -> Tuple[List[Mapping], List[Mapping], List[Mapping]]:
    """Return (keepalive, autofix, verifier) records parsed from NDJSON files."""
    keepalive: List[Mapping] = []
    autofix: List[Mapping] = []
    verifier: List[Mapping] = []

    for path in artifacts_dir.rglob("*.ndjson"):
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            if "attempt_number" in record or "trigger_reason" in record:
                autofix.append(record)
            elif "verdict" in record or "issues_created" in record:
                verifier.append(record)
            elif "iteration_count" in record or "stop_reason" in record:
                keepalive.append(record)

    return keepalive, autofix, verifier


def pct(numerator: int, denominator: int) -> float:
    return round((numerator / denominator * 100.0), 2) if denominator else 0.0


def summarize_keepalive(records: Sequence[Mapping]) -> MutableMapping:
    total = len(records)
    durations = [to_int(r.get("duration_seconds", 0) or 0) for r in records]
    iterations = [to_int(r.get("iteration_count", 0) or 0) for r in records]

    per_pr: MutableMapping[int, List[Mapping]] = collections.defaultdict(list)
    completions: set[int] = set()
    stop_reasons: MutableMapping[str, int] = collections.Counter()

    for record in records:
        pr_number = to_int(record.get("pr_number") or 0)
        per_pr[pr_number].append(record)
        stop_reason = str(record.get("stop_reason", "") or "").strip().lower()
        if stop_reason:
            stop_reasons[stop_reason] += 1

        tasks_total = to_int(record.get("tasks_total") or 0)
        tasks_completed = to_int(record.get("tasks_completed") or 0)
        action = str(record.get("action", "") or "").lower()
        completion_keywords = ("complete", "completed", "done", "success")
        reason_matches = any(word in stop_reason for word in completion_keywords)
        all_tasks_done = tasks_total > 0 and tasks_completed >= tasks_total

        if pr_number and (reason_matches or all_tasks_done or action in completion_keywords):
            completions.add(pr_number)

    unique_prs = len([pr for pr in per_pr.keys() if pr])
    completion_rate = pct(len(completions), unique_prs)

    return {
        "total_records": total,
        "unique_prs": unique_prs,
        "completion_rate": completion_rate,
        "average_duration_seconds": round(statistics.mean(durations), 2) if durations else 0.0,
        "average_iteration_count": round(statistics.mean(iterations), 2) if iterations else 0.0,
        "common_stop_reasons": dict(stop_reasons.most_common(5)),
    }


def summarize_autofix(records: Sequence[Mapping]) -> MutableMapping:
    total = len(records)
    fix_applied = sum(1 for r in records if bool(r.get("fix_applied")))
    gate_pass_after = sum(
        1
        for r in records
        if str(r.get("gate_result_after", "") or "").lower()
        in {"success", "succeeded", "completed", "pass", "passed"}
    )
    trigger_counts: MutableMapping[str, int] = collections.Counter(
        (str(r.get("trigger_reason", "") or "unknown").lower() for r in records)
    )

    return {
        "total_attempts": total,
        "fix_applied_count": fix_applied,
        "fix_applied_rate": pct(fix_applied, total),
        "gate_success_after_rate": pct(gate_pass_after, total),
        "trigger_reasons": dict(trigger_counts.most_common(5)),
    }


def summarize_verifier(records: Sequence[Mapping]) -> MutableMapping:
    total = len(records)
    verdict_counts: MutableMapping[str, int] = collections.Counter(
        (str(r.get("verdict", "") or "unknown").lower() for r in records)
    )
    issues_opened = sum(int(r.get("issues_created") or 0) for r in records)
    acceptance_counts = [int(r.get("acceptance_criteria_count") or 0) for r in records]

    return {
        "total_runs": total,
        "verdict_counts": dict(verdict_counts.most_common(5)),
        "issues_created_total": issues_opened,
        "average_acceptance_criteria": (
            round(statistics.mean(acceptance_counts), 2) if acceptance_counts else 0.0
        ),
    }


def render_markdown(
    keepalive_summary: Mapping,
    autofix_summary: Mapping,
    verifier_summary: Mapping,
    generated_at: dt.datetime,
) -> str:
    timestamp = generated_at.isoformat(timespec="seconds")
    if timestamp.endswith("+00:00"):
        timestamp = timestamp[:-6] + "Z"

    lines = [
        "# Agent workflow metrics",
        "",
        f"_Generated at {timestamp}_",
        "",
        "## Keepalive",
        f"- Records: **{keepalive_summary['total_records']}**",
        f"- Unique PRs: **{keepalive_summary['unique_prs']}**",
        f"- Keepalive completion rate (PRs completing without human intervention): **{keepalive_summary['completion_rate']}%**",
        f"- Average iteration count: **{keepalive_summary['average_iteration_count']}**",
        f"- Average duration (seconds): **{keepalive_summary['average_duration_seconds']}**",
    ]

    if keepalive_summary.get("common_stop_reasons"):
        lines.extend(
            ["- Common stop reasons:"]
            + [
                f"  - {reason}: {count}"
                for reason, count in keepalive_summary["common_stop_reasons"].items()
            ]
        )

    lines.extend(
        [
            "",
            "## Autofix",
            f"- Attempts: **{autofix_summary['total_attempts']}**",
            f"- Fix applied rate: **{autofix_summary['fix_applied_rate']}%** ({autofix_summary['fix_applied_count']} / {autofix_summary['total_attempts']})",
            f"- Gate success after autofix: **{autofix_summary['gate_success_after_rate']}%**",
        ]
    )

    if autofix_summary.get("trigger_reasons"):
        lines.extend(
            ["- Trigger reasons:"]
            + [
                f"  - {reason}: {count}"
                for reason, count in autofix_summary["trigger_reasons"].items()
            ]
        )

    lines.extend(
        [
            "",
            "## Verifier",
            f"- Runs: **{verifier_summary['total_runs']}**",
            f"- Verdicts: {', '.join(f'{k}: {v}' for k, v in verifier_summary['verdict_counts'].items()) or 'none'}",
            f"- Issues created: **{verifier_summary['issues_created_total']}**",
            f"- Average acceptance criteria counted: **{verifier_summary['average_acceptance_criteria']}**",
        ]
    )

    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate agent workflow metrics.")
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("artifacts"),
        help="Root directory containing metrics artifacts.",
    )
    parser.add_argument("--output", type=Path, help="Optional path to write markdown output.")
    args = parser.parse_args(argv)

    keepalive, autofix, verifier = load_records(args.artifacts_dir)
    summary = render_markdown(
        keepalive_summary=summarize_keepalive(keepalive),
        autofix_summary=summarize_autofix(autofix),
        verifier_summary=summarize_verifier(verifier),
        generated_at=dt.datetime.now(dt.timezone.utc),
    )

    if args.output:
        args.output.write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
