#!/usr/bin/env python3
"""Convenience CLI for emitting auto-pilot metrics records."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from scripts import autopilot_metrics_collector as collector


def _add_trace_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--langsmith-trace-id", help="LangSmith trace identifier")
    parser.add_argument("--langsmith-trace-url", help="LangSmith trace URL")


def _add_path_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--path",
        default="autopilot-metrics.ndjson",
        help="NDJSON output path",
    )


def _add_cycle_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--issue", required=True, help="Issue number")
    parser.add_argument("--cycle", required=True, help="Auto-pilot cycle count")
    parser.add_argument("--timestamp", help="ISO 8601 timestamp override")
    parser.add_argument("--max-cycles", help="Configured max cycle count")
    parser.add_argument("--steps-attempted", help="Steps attempted in the cycle")
    parser.add_argument("--steps-completed", help="Steps completed in the cycle")
    _add_trace_args(parser)
    _add_path_arg(parser)


def _cycle_record(args: argparse.Namespace, *, event: str) -> dict[str, Any]:
    record: dict[str, Any] = {
        "metric_type": "cycle",
        "issue_number": int(args.issue),
        "cycle_count": int(args.cycle),
        "cycle_event": event,
    }
    if args.timestamp:
        record["timestamp"] = args.timestamp
    if args.max_cycles is not None:
        record["max_cycles"] = int(args.max_cycles)
    if args.steps_attempted is not None:
        record["steps_attempted"] = int(args.steps_attempted)
    if args.steps_completed is not None:
        record["steps_completed"] = int(args.steps_completed)
    if args.langsmith_trace_id:
        record["langsmith_trace_id"] = args.langsmith_trace_id
    if args.langsmith_trace_url:
        record["langsmith_trace_url"] = args.langsmith_trace_url
    return record


def _summary_record(args: argparse.Namespace) -> dict[str, Any]:
    record: dict[str, Any] = {
        "metric_type": "cycle",
        "issue_number": int(args.issue),
        "cycle_count": int(args.total_cycles),
        "summary": True,
        "outcome": args.outcome,
    }
    if args.timestamp:
        record["timestamp"] = args.timestamp
    if args.max_cycles is not None:
        record["max_cycles"] = int(args.max_cycles)
    if args.steps_attempted is not None:
        record["steps_attempted"] = int(args.steps_attempted)
    if args.steps_completed is not None:
        record["steps_completed"] = int(args.steps_completed)
    if args.langsmith_trace_id:
        record["langsmith_trace_id"] = args.langsmith_trace_id
    if args.langsmith_trace_url:
        record["langsmith_trace_url"] = args.langsmith_trace_url
    return record


def _collector_args(*, path: str, args: list[str]) -> list[str]:
    return ["--path", path, *args]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Emit auto-pilot metrics records.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    cycle_start = subparsers.add_parser("emit-cycle-start", help="Emit a cycle start record")
    _add_cycle_args(cycle_start)

    cycle_end = subparsers.add_parser("emit-cycle-end", help="Emit a cycle end record")
    _add_cycle_args(cycle_end)

    step = subparsers.add_parser("emit-step", help="Emit a step record")
    step.add_argument("--issue", required=True, help="Issue number")
    step.add_argument("--cycle", required=True, help="Auto-pilot cycle count")
    step.add_argument("--step", required=True, help="Step name")
    step.add_argument("--timestamp", help="ISO 8601 timestamp override")
    step.add_argument("--duration-ms", help="Duration in milliseconds")
    step.add_argument("--started-at", help="ISO 8601 start timestamp")
    step.add_argument("--ended-at", help="ISO 8601 end timestamp")
    step.add_argument("--started-at-ms", help="Epoch milliseconds start timestamp")
    step.add_argument("--ended-at-ms", help="Epoch milliseconds end timestamp")
    step.add_argument("--success", required=True, help="Whether the step succeeded")
    step.add_argument("--failure-reason", help="Failure reason when success is false")
    _add_trace_args(step)
    _add_path_arg(step)

    escalation = subparsers.add_parser("emit-escalation", help="Emit an escalation record")
    escalation.add_argument("--issue", required=True, help="Issue number")
    escalation.add_argument("--cycle", required=True, help="Auto-pilot cycle count")
    escalation.add_argument("--reason", required=True, help="Escalation reason")
    escalation.add_argument("--timestamp", help="ISO 8601 timestamp override")
    _add_trace_args(escalation)
    _add_path_arg(escalation)

    summary = subparsers.add_parser("emit-summary", help="Emit a summary record")
    summary.add_argument("--issue", required=True, help="Issue number")
    summary.add_argument("--total-cycles", required=True, help="Total cycle count")
    summary.add_argument(
        "--outcome",
        required=True,
        choices=["completed", "failed", "needs-human", "paused"],
        help="Final outcome",
    )
    summary.add_argument("--timestamp", help="ISO 8601 timestamp override")
    summary.add_argument("--max-cycles", help="Configured max cycle count")
    summary.add_argument("--steps-attempted", help="Steps attempted in the run")
    summary.add_argument("--steps-completed", help="Steps completed in the run")
    _add_trace_args(summary)
    _add_path_arg(summary)

    subparsers.add_parser("print-schema", help="Print metrics schema and exit")

    return parser


def _emit_record(record: dict[str, Any], path: str) -> int:
    payload = json.dumps(record, separators=(",", ":"))
    args = _collector_args(path=path, args=["--record-json", payload])
    return collector.main(args)


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "print-schema":
        print(collector.schema_payload())
        return 0

    path = args.path

    if args.command == "emit-cycle-start":
        return _emit_record(_cycle_record(args, event="start"), path)
    if args.command == "emit-cycle-end":
        return _emit_record(_cycle_record(args, event="end"), path)
    if args.command == "emit-summary":
        return _emit_record(_summary_record(args), path)
    if args.command == "emit-step":
        collector_args = [
            "--metric-type",
            "step",
            "--issue-number",
            args.issue,
            "--cycle-count",
            args.cycle,
            "--step-name",
            args.step,
            "--success",
            args.success,
        ]
        if args.timestamp:
            collector_args.extend(["--timestamp", args.timestamp])
        if args.duration_ms:
            collector_args.extend(["--duration-ms", args.duration_ms])
        if args.started_at:
            collector_args.extend(["--started-at", args.started_at])
        if args.ended_at:
            collector_args.extend(["--ended-at", args.ended_at])
        if args.started_at_ms:
            collector_args.extend(["--started-at-ms", args.started_at_ms])
        if args.ended_at_ms:
            collector_args.extend(["--ended-at-ms", args.ended_at_ms])
        if args.failure_reason:
            collector_args.extend(["--failure-reason", args.failure_reason])
        if args.langsmith_trace_id:
            collector_args.extend(["--langsmith-trace-id", args.langsmith_trace_id])
        if args.langsmith_trace_url:
            collector_args.extend(["--langsmith-trace-url", args.langsmith_trace_url])
        return collector.main(_collector_args(path=path, args=collector_args))
    if args.command == "emit-escalation":
        collector_args = [
            "--metric-type",
            "escalation",
            "--issue-number",
            args.issue,
            "--cycle-count",
            args.cycle,
            "--escalation-reason",
            args.reason,
        ]
        if args.timestamp:
            collector_args.extend(["--timestamp", args.timestamp])
        if args.langsmith_trace_id:
            collector_args.extend(["--langsmith-trace-id", args.langsmith_trace_id])
        if args.langsmith_trace_url:
            collector_args.extend(["--langsmith-trace-url", args.langsmith_trace_url])
        return collector.main(_collector_args(path=path, args=collector_args))

    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main(sys.argv[1:]))
