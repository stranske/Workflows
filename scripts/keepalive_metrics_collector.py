#!/usr/bin/env python3
"""Append structured keepalive metrics records to an NDJSON log."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = (
    "pr_number",
    "iteration",
    "timestamp",
    "action",
    "error_category",
    "duration_ms",
    "tasks_total",
    "tasks_complete",
)


@dataclass(frozen=True)
class ValidationError(Exception):
    """Raised when a record fails schema validation."""

    message: str

    def __str__(self) -> str:
        return self.message


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_timestamp(value: str) -> datetime:
    if not value:
        raise ValidationError("timestamp is required")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError(f"timestamp must be ISO 8601: {value}") from exc
    if parsed.tzinfo is None:
        raise ValidationError("timestamp must include timezone")
    return parsed


def validate_record(record: dict[str, Any]) -> None:
    """Validate required fields and types for a metrics record."""
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    if missing:
        raise ValidationError(f"missing fields: {', '.join(missing)}")

    if not _is_int(record["pr_number"]):
        raise ValidationError("pr_number must be an integer")
    if not _is_int(record["iteration"]):
        raise ValidationError("iteration must be an integer")
    if not isinstance(record["action"], str) or not record["action"].strip():
        raise ValidationError("action must be a non-empty string")
    if not isinstance(record["error_category"], str) or not record["error_category"].strip():
        raise ValidationError("error_category must be a non-empty string")
    if not _is_int(record["duration_ms"]):
        raise ValidationError("duration_ms must be an integer")
    if not _is_int(record["tasks_total"]):
        raise ValidationError("tasks_total must be an integer")
    if not _is_int(record["tasks_complete"]):
        raise ValidationError("tasks_complete must be an integer")

    _parse_timestamp(str(record["timestamp"]))


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce_int(value: str, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be an integer") from exc


def build_record_from_args(args: argparse.Namespace) -> dict[str, Any]:
    record = {
        "pr_number": _coerce_int(args.pr_number, "pr_number"),
        "iteration": _coerce_int(args.iteration, "iteration"),
        "timestamp": args.timestamp or _utc_now_iso(),
        "action": args.action,
        "error_category": args.error_category,
        "duration_ms": _coerce_int(args.duration_ms, "duration_ms"),
        "tasks_total": _coerce_int(args.tasks_total, "tasks_total"),
        "tasks_complete": _coerce_int(args.tasks_complete, "tasks_complete"),
    }
    return record


def load_record_from_json(payload: str) -> dict[str, Any]:
    try:
        record = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValidationError("record_json must be valid JSON") from exc
    if not isinstance(record, dict):
        raise ValidationError("record_json must decode to an object")
    if "timestamp" not in record:
        record["timestamp"] = _utc_now_iso()
    return record


def append_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, separators=(",", ":"), sort_keys=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload + "\n")


def _iter_errors(error: Exception) -> Iterable[str]:
    if isinstance(error, ValidationError):
        yield str(error)
    else:
        yield str(error)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Append keepalive metrics record to NDJSON log.")
    parser.add_argument("--path", default="keepalive-metrics.ndjson", help="NDJSON output path")
    parser.add_argument("--record-json", help="JSON object payload for the record")
    parser.add_argument("--pr-number", help="Pull request number")
    parser.add_argument("--iteration", help="Keepalive iteration")
    parser.add_argument("--timestamp", help="ISO 8601 timestamp (defaults to now)")
    parser.add_argument("--action", help="Action taken during iteration")
    parser.add_argument("--error-category", help="Error category or 'none'")
    parser.add_argument("--duration-ms", help="Iteration duration in milliseconds")
    parser.add_argument("--tasks-total", help="Total tasks detected")
    parser.add_argument("--tasks-complete", help="Tasks completed")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.record_json:
            record = load_record_from_json(args.record_json)
        else:
            required_args = [
                args.pr_number,
                args.iteration,
                args.action,
                args.error_category,
                args.duration_ms,
                args.tasks_total,
                args.tasks_complete,
            ]
            if any(value is None for value in required_args):
                raise ValidationError("missing required field arguments")
            record = build_record_from_args(args)
        validate_record(record)
        append_record(Path(args.path), record)
    except Exception as exc:
        for message in _iter_errors(exc):
            print(f"keepalive_metrics_collector: {message}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
