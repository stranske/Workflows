"""
Aggregate agent workflow metrics from NDJSON artifacts and emit a Markdown summary.

Usage:
    python scripts/aggregate_agent_metrics.py --input artifacts/ --output summary.md
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        "-i",
        action="append",
        default=[],
        help="File or directory containing NDJSON metrics (can be passed multiple times).",
    )
    parser.add_argument(
        "--recent-days",
        type=int,
        default=35,
        help="Only include metrics recorded in the last N days (default: 35).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="",
        help="Optional file path to write the Markdown summary.",
    )
    return parser.parse_args()


def iter_ndjson(paths: Iterable[Path]) -> Iterable[Tuple[Dict, Path]]:
    for path in paths:
        if path.is_dir():
            yield from iter_ndjson(path.rglob("*.ndjson"))
            continue
        if path.suffix.lower() != ".ndjson":
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    yield json.loads(line), path
                except json.JSONDecodeError:
                    continue
        except FileNotFoundError:
            continue


def _parse_datetime(value: str):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_metrics(paths: Iterable[Path], recent_days: int):
    cutoff = datetime.now(timezone.utc) - timedelta(days=recent_days)
    keepalive, autofix, verifier = [], [], []
    for record, source in iter_ndjson(paths):
        if not isinstance(record, dict):
            continue
        recorded_at = _parse_datetime(str(record.get("recorded_at", ""))) or cutoff
        if recorded_at < cutoff:
            continue
        # Try to infer record type
        if "iteration_count" in record:
            keepalive.append(record)
        elif "attempt_number" in record:
            autofix.append(record)
        elif "verdict" in record:
            verifier.append(record)
        else:
            # Fallback to filename hint
            name = source.name.lower()
            if "keepalive" in name:
                keepalive.append(record)
            elif "autofix" in name:
                autofix.append(record)
            elif "verifier" in name:
                verifier.append(record)
    return keepalive, autofix, verifier


def summarise_keepalive(records: List[Dict]) -> Dict[str, object]:
    if not records:
        return {
            "count": 0,
            "pr_count": 0,
            "avg_iterations": 0.0,
            "completion_pct": 0.0,
            "top_stop_reasons": [],
        }

    stop_reasons = Counter()
    iterations: List[int] = []
    pr_counts = Counter()
    completed_prs = set()

    for rec in records:
        pr = int(rec.get("pr_number") or 0)
        pr_counts[pr] += 1
        iterations.append(int(rec.get("iteration_count") or 0))
        stop = str(rec.get("stop_reason", "")).lower()
        if stop:
            stop_reasons[stop] += 1
        tasks_total = int(rec.get("tasks_total") or 0)
        tasks_completed = int(rec.get("tasks_completed") or 0)

        if "complete" in stop or (tasks_total > 0 and tasks_completed >= tasks_total):
            completed_prs.add(pr)

    avg_iterations = statistics.mean(iterations) if iterations else 0.0
    pr_total = len(pr_counts)
    completion_pct = (len(completed_prs) / pr_total * 100.0) if pr_total else 0.0
    top_stop_reasons = stop_reasons.most_common(5)

    return {
        "count": len(records),
        "pr_count": pr_total,
        "avg_iterations": round(avg_iterations, 2),
        "completion_pct": round(completion_pct, 2),
        "top_stop_reasons": top_stop_reasons,
    }


def summarise_autofix(records: List[Dict]) -> Dict[str, object]:
    if not records:
        return {
            "count": 0,
            "pr_count": 0,
            "success_pct": 0.0,
            "avg_attempts": 0.0,
        }
    pr_attempts: defaultdict[int, List[int]] = defaultdict(list)
    success = 0
    for rec in records:
        pr_raw = rec.get("pr_number")
        pr: int | None = None
        if pr_raw is not None:
            try:
                pr_int = int(pr_raw)
                if pr_int > 0:
                    pr = pr_int
    successful_prs = set()
    for rec in records:
        pr = int(rec.get("pr_number") or 0)
        attempt = int(rec.get("attempt_number") or 0)
        pr_attempts[pr].append(attempt)
        if rec.get("fix_applied"):
            successful_prs.add(pr)
    avg_attempts = (
        statistics.mean(max(v) for v in pr_attempts.values()) if pr_attempts else 0.0
    )
    success_pct = (
        (len(successful_prs) / len(pr_attempts) * 100.0) if pr_attempts else 0.0
    )
    return {
        "count": len(records),
        "pr_count": len(pr_attempts),
        "success_pct": round(success_pct, 2),
        "avg_attempts": round(avg_attempts, 2),
    }


def summarise_verifier(records: List[Dict]) -> Dict[str, object]:
    if not records:
        return {
            "count": 0,
            "pass_pct": 0.0,
            "avg_checks": 0.0,
            "issues_created": 0,
        }
    verdicts = Counter()
    checks: List[int] = []
    issues_created = 0
    for rec in records:
        verdict = str(rec.get("verdict", "unknown")).lower()
        verdicts[verdict] += 1
        checks.append(int(rec.get("checks_run") or 0))
        issues_created += int(rec.get("issues_created") or 0)

    pass_total = verdicts.get("pass", 0)
    total = sum(verdicts.values())
    pass_pct = (pass_total / total * 100.0) if total else 0.0
    avg_checks = statistics.mean(checks) if checks else 0.0
    return {
        "count": total,
        "pass_pct": round(pass_pct, 2),
        "avg_checks": round(avg_checks, 2),
        "issues_created": issues_created,
        "verdicts": verdicts.most_common(),
    }


def build_markdown(
    keepalive_summary: Dict[str, object],
    autofix_summary: Dict[str, object],
    verifier_summary: Dict[str, object],
    recent_days: int,
) -> str:
    lines = [
        "# Weekly agent metrics summary",
        "",
        f"_Covers metrics from the last **{recent_days} days**._",
        "",
        "## Keepalive loop",
        f"- Records analyzed: **{keepalive_summary['count']}** across **{keepalive_summary['pr_count']} PRs**",
        f"- Average iterations per record: **{keepalive_summary['avg_iterations']}**",
        f"- PRs completed via keepalive: **{keepalive_summary['completion_pct']}%**",
    ]

    top_stops = keepalive_summary.get("top_stop_reasons") or []
    if top_stops:
        lines.append("- Top stop reasons:")
        for reason, count in top_stops:
            lines.append(f"  - `{reason or 'unknown'}` — {count}")

    lines += [
        "",
        "## Autofix loop",
        f"- Records analyzed: **{autofix_summary['count']}** across **{autofix_summary['pr_count']} PRs**",
        f"- Fix applied success rate: **{autofix_summary['success_pct']}%**",
        f"- Average attempts per PR (max): **{autofix_summary['avg_attempts']}**",
        "",
        "## Verifier",
        f"- Records analyzed: **{verifier_summary['count']}**",
        f"- Pass rate: **{verifier_summary['pass_pct']}%**",
        f"- Average checks run: **{verifier_summary['avg_checks']}**",
        f"- Issues created: **{verifier_summary['issues_created']}**",
    ]

    verdicts = verifier_summary.get("verdicts") or []
    if verdicts:
        lines.append("- Verdict distribution:")
        for verdict, count in verdicts:
            lines.append(f"  - `{verdict}` — {count}")

    lines.append("")
    lines.append("## Key question: keepalive completion rate")
    lines.append(
        f"- Percentage of PRs completing via keepalive without human intervention: **{keepalive_summary['completion_pct']}%**"
    )
    return "\n".join(lines) + "\n"


def main():
    args = parse_args()
    inputs = [Path(p) for p in (args.input or [])]
    if not inputs:
        inputs = [Path("metrics-artifacts"), Path("artifacts"), Path(".")]

    keepalive_records, autofix_records, verifier_records = load_metrics(
        inputs, args.recent_days
    )

    keepalive_summary = summarise_keepalive(keepalive_records)
    autofix_summary = summarise_autofix(autofix_records)
    verifier_summary = summarise_verifier(verifier_records)

    markdown = build_markdown(
        keepalive_summary, autofix_summary, verifier_summary, args.recent_days
    )
    print(markdown)

    output_path = Path(args.output) if args.output else None
    if output_path:
        output_path.write_text(markdown, encoding="utf-8")


if __name__ == "__main__":
    main()
