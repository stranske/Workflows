#!/usr/bin/env python3
"""Aggregate agent metrics NDJSON into a markdown summary."""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

_DEFAULT_METRICS_DIR = "agent-metrics"
_DEFAULT_OUTPUT = "agent-metrics-summary.md"


def _parse_timestamp(value: Any) -> _dt.datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return _dt.datetime.fromtimestamp(float(value), tz=_dt.UTC)
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = _dt.datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_dt.UTC)
        return parsed
    return None


def _gather_metrics_files(metrics_paths: list[str], metrics_dir: str) -> list[Path]:
    if metrics_paths:
        return [Path(path) for path in metrics_paths if path]

    root = Path(metrics_dir)
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.ndjson") if path.is_file())


def _read_ndjson(files: Iterable[Path]) -> tuple[list[dict[str, Any]], int]:
    entries: list[dict[str, Any]] = []
    errors = 0
    for path in files:
        try:
            handle = path.open("r", encoding="utf-8")
        except OSError:
            errors += 1
            continue
        with handle:
            for line in handle:
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


def _classify_entry(entry: dict[str, Any]) -> str:
    schema = entry.get("schema")
    if schema == "workflows-terminal-disposition/v1":
        return "terminal_disposition"
    explicit = entry.get("metric_type") or entry.get("type") or entry.get("workflow")
    if isinstance(explicit, str):
        lowered = explicit.lower()
        if "keepalive" in lowered:
            return "keepalive"
        if "autofix" in lowered:
            return "autofix"
        if "verifier" in lowered or "verify" in lowered:
            return "verifier"
        if lowered in ("step", "cycle", "escalation"):
            return "autopilot"
    if any(key in entry for key in ("iteration_count", "stop_reason", "tasks_total")):
        return "keepalive"
    if any(key in entry for key in ("attempt_number", "trigger_reason", "fix_applied")):
        return "autofix"
    if any(key in entry for key in ("verdict", "issues_created", "acceptance_criteria_count")):
        return "verifier"
    # Auto-pilot step/cycle records have step_name + duration_ms
    if "step_name" in entry and "duration_ms" in entry:
        return "autopilot"
    if "escalation_reason" in entry:
        return "autopilot"
    return "unknown"


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


def _summarise_keepalive(entries: list[dict[str, Any]]) -> dict[str, Any]:
    stop_reasons = Counter()
    gate_results = Counter()
    iterations: list[int] = []
    prs: set[int] = set()
    tasks_complete = 0
    for entry in entries:
        stop_reason = entry.get("stop_reason")
        if stop_reason:
            stop_reasons[str(stop_reason)] += 1
        gate = entry.get("gate_conclusion") or entry.get("gate_result")
        if gate:
            gate_results[str(gate)] += 1
        iteration = _safe_int(entry.get("iteration_count") or entry.get("iteration"))
        if iteration is not None:
            iterations.append(iteration)
        pr_number = _safe_int(entry.get("pr_number") or entry.get("pr"))
        if pr_number is not None:
            prs.add(pr_number)
        if stop_reason == "tasks-complete":
            tasks_complete += 1
    avg_iterations = sum(iterations) / len(iterations) if iterations else 0.0
    return {
        "runs": len(entries),
        "prs": len(prs),
        "avg_iterations": avg_iterations,
        "stop_reasons": stop_reasons,
        "gate_results": gate_results,
        "tasks_complete": tasks_complete,
    }


def _summarise_autofix(entries: list[dict[str, Any]]) -> dict[str, Any]:
    triggers = Counter()
    gate_results = Counter()
    prs: set[int] = set()
    fixes_applied = 0
    for entry in entries:
        trigger = entry.get("trigger_reason")
        if trigger:
            triggers[str(trigger)] += 1
        gate = entry.get("gate_result_after") or entry.get("gate_result")
        if gate:
            gate_results[str(gate)] += 1
        pr_number = _safe_int(entry.get("pr_number") or entry.get("pr"))
        if pr_number is not None:
            prs.add(pr_number)
        if entry.get("fix_applied") in (True, "true", "True", "1", 1):
            fixes_applied += 1
    return {
        "attempts": len(entries),
        "prs": len(prs),
        "fixes_applied": fixes_applied,
        "triggers": triggers,
        "gate_results": gate_results,
    }


def _summarise_verifier(entries: list[dict[str, Any]]) -> dict[str, Any]:
    verdicts = Counter()
    terminal_dispositions = Counter()
    terminal_sources = Counter()
    verifier_run_keys: set[str] = set()
    prs: set[int] = set()
    issues_created = 0
    acceptance_counts: list[int] = []
    terminal_records = 0
    for index, entry in enumerate(entries):
        is_terminal_disposition = entry.get("schema") == "workflows-terminal-disposition/v1"
        if not is_terminal_disposition:
            run_id = entry.get("run_id") or entry.get("workflow_run_id")
            run_attempt = entry.get("run_attempt")
            pr_number_for_key = _safe_int(entry.get("pr_number") or entry.get("pr"))
            if run_id:
                verifier_run_keys.add(f"run:{run_id}:attempt:{run_attempt or ''}")
            elif pr_number_for_key is not None:
                verifier_run_keys.add(f"pr:{pr_number_for_key}")
            else:
                verifier_run_keys.add(f"entry:{index}")

        verdict = entry.get("verdict")
        if verdict:
            verdicts[str(verdict)] += 1
        if is_terminal_disposition:
            terminal_records += 1
            disposition = entry.get("disposition") or entry.get("terminal_state") or "unknown"
            terminal_dispositions[str(disposition)] += 1
            source_type = entry.get("source_type") or "unknown"
            source_id = entry.get("source_id") or "unknown"
            terminal_sources[f"{source_type}:{source_id}"] += 1
        pr_number = _safe_int(entry.get("pr_number") or entry.get("pr"))
        if pr_number is not None:
            prs.add(pr_number)
        created = _safe_int(entry.get("issues_created"))
        if created is not None:
            issues_created += created
        acceptance = _safe_int(entry.get("acceptance_criteria_count"))
        if acceptance is not None:
            acceptance_counts.append(acceptance)
    avg_acceptance = sum(acceptance_counts) / len(acceptance_counts) if acceptance_counts else 0.0
    return {
        "runs": len(verifier_run_keys),
        "prs": len(prs),
        "verdicts": verdicts,
        "issues_created": issues_created,
        "avg_acceptance": avg_acceptance,
        "terminal_records": terminal_records,
        "terminal_dispositions": terminal_dispositions,
        "terminal_sources": terminal_sources,
    }


def _summarise_autopilot(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise auto-pilot step/cycle/escalation records."""
    issues: set[int] = set()
    step_durations: dict[str, list[float]] = {}
    step_successes: dict[str, int] = {}
    step_failures: dict[str, int] = {}
    failure_reasons = Counter()
    escalation_reasons = Counter()
    escalation_count = 0
    needs_human_count = 0

    for entry in entries:
        issue_num = _safe_int(entry.get("issue_number") or entry.get("issue"))
        if issue_num is not None:
            issues.add(issue_num)

        metric_type = entry.get("metric_type", "")

        if metric_type == "escalation":
            escalation_count += 1
            reason = entry.get("escalation_reason", "unknown")
            escalation_reasons[str(reason)] += 1
            if "needs-human" in str(reason).lower() or "needs_human" in str(reason).lower():
                needs_human_count += 1
            continue

        step_name = entry.get("step_name")
        if not step_name:
            continue

        duration = _safe_float(entry.get("duration_ms"))
        if duration is not None:
            step_durations.setdefault(step_name, []).append(duration)

        success = entry.get("success")
        if success in (True, "true", "True", "1", 1):
            step_successes[step_name] = step_successes.get(step_name, 0) + 1
        elif success in (False, "false", "False", "0", 0):
            step_failures[step_name] = step_failures.get(step_name, 0) + 1
            reason = entry.get("failure_reason", "unknown")
            if reason and reason != "none":
                failure_reasons[str(reason)] += 1

    # Compute per-step averages
    step_avg_duration: dict[str, float] = {}
    for step, durations in step_durations.items():
        step_avg_duration[step] = sum(durations) / len(durations) if durations else 0.0

    total_steps = sum(step_successes.values()) + sum(step_failures.values())

    return {
        "records": len(entries),
        "issues": len(issues),
        "total_steps": total_steps,
        "step_avg_duration_ms": step_avg_duration,
        "step_successes": step_successes,
        "step_failures": step_failures,
        "failure_reasons": failure_reasons,
        "escalation_count": escalation_count,
        "escalation_reasons": escalation_reasons,
        "needs_human_count": needs_human_count,
    }


def _format_counter(counter: Counter[str]) -> str:
    if not counter:
        return "n/a"
    parts = [f"{key} ({count})" for key, count in counter.most_common()]
    return ", ".join(parts)


def _format_rate(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "n/a"
    rate = (numerator / denominator) * 100
    return f"{rate:.1f}% ({numerator}/{denominator})"


def build_summary(entries: list[dict[str, Any]], errors: int) -> str:
    buckets: dict[str, list[dict[str, Any]]] = {
        "keepalive": [],
        "autofix": [],
        "verifier": [],
        "terminal_disposition": [],
        "autopilot": [],
        "unknown": [],
    }
    timestamps: list[_dt.datetime] = []

    for entry in entries:
        bucket = _classify_entry(entry)
        buckets.setdefault(bucket, []).append(entry)
        for key in ("timestamp", "created_at", "time", "run_started_at"):
            ts = _parse_timestamp(entry.get(key))
            if ts is not None:
                timestamps.append(ts)
                break

    keepalive = _summarise_keepalive(buckets["keepalive"])
    autofix = _summarise_autofix(buckets["autofix"])
    verifier = _summarise_verifier(buckets["verifier"] + buckets["terminal_disposition"])
    autopilot = _summarise_autopilot(buckets["autopilot"])

    now = _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    lines = [
        "# Agent Metrics Summary",
        "",
        f"Generated: {now}",
        (
            f"Records: {len(entries)} "
            f"(keepalive {keepalive['runs']}, autofix {autofix['attempts']}, "
            f"verifier {verifier['runs']}, "
            f"terminal dispositions {verifier['terminal_records']}, "
            f"autopilot {autopilot['records']}, "
            f"unknown {len(buckets['unknown'])})"
        ),
        f"Parse errors: {errors}",
    ]

    if timestamps:
        earliest = min(timestamps).isoformat().replace("+00:00", "Z")
        latest = max(timestamps).isoformat().replace("+00:00", "Z")
        lines.append(f"Range: {earliest} to {latest}")

    lines.extend(
        [
            "",
            "## Keepalive",
            f"- Runs: {keepalive['runs']}",
            f"- PRs: {keepalive['prs']}",
            f"- Avg iterations: {keepalive['avg_iterations']:.1f}",
            f"- Stop reasons: {_format_counter(keepalive['stop_reasons'])}",
            f"- Gate conclusions: {_format_counter(keepalive['gate_results'])}",
            f"- Tasks complete rate: {_format_rate(keepalive['tasks_complete'], keepalive['runs'])}",
            "",
            "## Autofix",
            f"- Attempts: {autofix['attempts']}",
            f"- PRs: {autofix['prs']}",
            f"- Fixes applied: {_format_rate(autofix['fixes_applied'], autofix['attempts'])}",
            f"- Trigger reasons: {_format_counter(autofix['triggers'])}",
            f"- Gate results after: {_format_counter(autofix['gate_results'])}",
            "",
            "## Verifier",
            f"- Runs: {verifier['runs']}",
            f"- PRs: {verifier['prs']}",
            f"- Verdicts: {_format_counter(verifier['verdicts'])}",
            f"- Issues created: {verifier['issues_created']}",
            f"- Avg acceptance criteria: {verifier['avg_acceptance']:.1f}",
            f"- Terminal disposition records: {verifier['terminal_records']}",
            f"- Terminal dispositions: {_format_counter(verifier['terminal_dispositions'])}",
            f"- Terminal disposition sources: {_format_counter(verifier['terminal_sources'])}",
        ]
    )

    # ── Auto-pilot pipeline section ──────────────────────────────────
    if autopilot["records"] > 0:
        lines.extend(
            [
                "",
                "## Auto-Pilot Pipeline",
                f"- Records: {autopilot['records']}",
                f"- Issues: {autopilot['issues']}",
                f"- Total step executions: {autopilot['total_steps']}",
                f"- Escalations: {autopilot['escalation_count']}",
                f"- Needs-human escalation rate: {_format_rate(autopilot['needs_human_count'], autopilot['escalation_count'])}",
                f"- Escalation reasons: {_format_counter(autopilot['escalation_reasons'])}",
                f"- Failure reasons: {_format_counter(autopilot['failure_reasons'])}",
            ]
        )

        if autopilot["step_avg_duration_ms"]:
            lines.append("")
            lines.append("### Step Average Durations")
            for step, avg_ms in sorted(autopilot["step_avg_duration_ms"].items()):
                avg_s = avg_ms / 1000.0
                successes = autopilot["step_successes"].get(step, 0)
                failures = autopilot["step_failures"].get(step, 0)
                total = successes + failures
                lines.append(
                    f"- {step}: {avg_s:.1f}s avg ({_format_rate(successes, total)} success)"
                )

    return "\n".join(lines) + "\n"


def main() -> int:
    metrics_paths_raw = os.environ.get("METRICS_PATHS", "")
    metrics_paths = [item.strip() for item in metrics_paths_raw.split(",") if item.strip()]
    metrics_dir = os.environ.get("METRICS_DIR", _DEFAULT_METRICS_DIR)
    output_path = Path(os.environ.get("OUTPUT_PATH", _DEFAULT_OUTPUT))

    files = _gather_metrics_files(metrics_paths, metrics_dir)
    if not files:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("No metrics files found to aggregate.\n", encoding="utf-8")
        print("No metrics files found to aggregate.", file=sys.stderr)
        return 0

    entries, errors = _read_ndjson(files)
    summary = build_summary(entries, errors)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(summary, encoding="utf-8")
    print(f"Wrote metrics summary to {output_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
