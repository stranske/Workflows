#!/usr/bin/env python3
"""Append structured auto-pilot metrics records to an NDJSON log.

Schema (version 1):
{
  "metric_type": "step" | "cycle" | "escalation",
  "issue_number": int,
  "timestamp": "YYYY-MM-DDTHH:MM:SSZ",
  "cycle_count": int,

  // step records
  "step_name": str,
  "duration_ms": int,
  "success": bool,
  "failure_reason": str,

  // cycle records (optional extras)
  "max_cycles": int?,
  "steps_attempted": int?,
  "steps_completed": int?,

  // escalation records
  "escalation_reason": str
}

NOTE: agents-auto-pilot workflow updates are required to emit step metrics per step
(needs-human label) because workflow files are protected in agent-standard runs. Use
start/end timestamps (e.g., epoch milliseconds) and pass them via --started-at-ms/--ended-at-ms.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AUTOPILOT_METRICS_SCHEMA_VERSION = 1

AUTOPILOT_METRICS_SCHEMA: dict[str, Any] = {
    "version": AUTOPILOT_METRICS_SCHEMA_VERSION,
    "record_types": {
        "step": {
            "required": (
                "schema_version",
                "metric_type",
                "issue_number",
                "timestamp",
                "cycle_count",
                "step_name",
                "duration_ms",
                "success",
                "failure_reason",
            ),
        },
        "cycle": {
            "required": (
                "schema_version",
                "metric_type",
                "issue_number",
                "timestamp",
                "cycle_count",
            ),
            "optional": ("max_cycles", "steps_attempted", "steps_completed"),
        },
        "escalation": {
            "required": (
                "schema_version",
                "metric_type",
                "issue_number",
                "timestamp",
                "cycle_count",
                "escalation_reason",
            ),
        },
    },
}

STEP_REQUIRED_FIELDS = AUTOPILOT_METRICS_SCHEMA["record_types"]["step"]["required"]
CYCLE_REQUIRED_FIELDS = AUTOPILOT_METRICS_SCHEMA["record_types"]["cycle"]["required"]
ESCALATION_REQUIRED_FIELDS = AUTOPILOT_METRICS_SCHEMA["record_types"]["escalation"]["required"]
_CYCLE_OPTIONAL_FIELDS = AUTOPILOT_METRICS_SCHEMA["record_types"]["cycle"]["optional"]


def schema_payload() -> str:
    """Return the JSON schema payload for documentation or tooling."""
    return json.dumps(AUTOPILOT_METRICS_SCHEMA, sort_keys=True, indent=2)


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


def _duration_ms_from_bounds(started_at: str, ended_at: str) -> int:
    start = _parse_timestamp(started_at)
    end = _parse_timestamp(ended_at)
    delta_ms = int((end - start).total_seconds() * 1000)
    if delta_ms < 0:
        raise ValidationError("ended_at must be after started_at")
    return delta_ms


def _utc_now_epoch_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def _duration_ms_from_epoch_bounds(started_at_ms: int, ended_at_ms: int) -> int:
    delta_ms = ended_at_ms - started_at_ms
    if delta_ms < 0:
        raise ValidationError("ended_at_ms must be after started_at_ms")
    return delta_ms


def _validate_step(record: dict[str, Any]) -> None:
    missing = [field for field in STEP_REQUIRED_FIELDS if field not in record]
    if missing:
        raise ValidationError(f"missing fields: {', '.join(missing)}")

    if not _is_int(record["schema_version"]):
        raise ValidationError("schema_version must be an integer")
    if record["schema_version"] != AUTOPILOT_METRICS_SCHEMA_VERSION:
        raise ValidationError(f"schema_version must be {AUTOPILOT_METRICS_SCHEMA_VERSION}")
    if not _is_int(record["issue_number"]):
        raise ValidationError("issue_number must be an integer")
    if not _is_int(record["cycle_count"]):
        raise ValidationError("cycle_count must be an integer")
    if not isinstance(record["step_name"], str) or not record["step_name"].strip():
        raise ValidationError("step_name must be a non-empty string")
    if not _is_int(record["duration_ms"]):
        raise ValidationError("duration_ms must be an integer")
    if not isinstance(record["success"], bool):
        raise ValidationError("success must be a boolean")
    if not isinstance(record["failure_reason"], str):
        raise ValidationError("failure_reason must be a string")
    if record["success"] is False and not record["failure_reason"].strip():
        raise ValidationError("failure_reason must be set when success is false")

    _parse_timestamp(str(record["timestamp"]))


def _validate_cycle(record: dict[str, Any]) -> None:
    missing = [field for field in CYCLE_REQUIRED_FIELDS if field not in record]
    if missing:
        raise ValidationError(f"missing fields: {', '.join(missing)}")

    if not _is_int(record["schema_version"]):
        raise ValidationError("schema_version must be an integer")
    if record["schema_version"] != AUTOPILOT_METRICS_SCHEMA_VERSION:
        raise ValidationError(f"schema_version must be {AUTOPILOT_METRICS_SCHEMA_VERSION}")
    if not _is_int(record["issue_number"]):
        raise ValidationError("issue_number must be an integer")
    if not _is_int(record["cycle_count"]):
        raise ValidationError("cycle_count must be an integer")

    for field in _CYCLE_OPTIONAL_FIELDS:
        if field in record and not _is_int(record[field]):
            raise ValidationError(f"{field} must be an integer")

    _parse_timestamp(str(record["timestamp"]))


def _validate_escalation(record: dict[str, Any]) -> None:
    missing = [field for field in ESCALATION_REQUIRED_FIELDS if field not in record]
    if missing:
        raise ValidationError(f"missing fields: {', '.join(missing)}")

    if not _is_int(record["schema_version"]):
        raise ValidationError("schema_version must be an integer")
    if record["schema_version"] != AUTOPILOT_METRICS_SCHEMA_VERSION:
        raise ValidationError(f"schema_version must be {AUTOPILOT_METRICS_SCHEMA_VERSION}")
    if not _is_int(record["issue_number"]):
        raise ValidationError("issue_number must be an integer")
    if not _is_int(record["cycle_count"]):
        raise ValidationError("cycle_count must be an integer")
    if not isinstance(record["escalation_reason"], str) or not record["escalation_reason"].strip():
        raise ValidationError("escalation_reason must be a non-empty string")

    _parse_timestamp(str(record["timestamp"]))


def validate_record(record: dict[str, Any]) -> None:
    """Validate required fields and types for a metrics record."""
    metric_type = str(record.get("metric_type", "")).strip().lower()
    if not metric_type:
        raise ValidationError("metric_type must be set")
    if metric_type == "step":
        _validate_step(record)
        return
    if metric_type == "cycle":
        _validate_cycle(record)
        return
    if metric_type == "escalation":
        _validate_escalation(record)
        return
    raise ValidationError("metric_type must be 'step', 'cycle', or 'escalation'")


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce_int(value: str | int | None, field: str) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be an integer") from exc


def _coerce_bool(value: str | bool | None, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        raise ValidationError(f"{field} must be a boolean")
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValidationError(f"{field} must be a boolean")


def _env_or_value(value: str | None, env_name: str) -> str | None:
    if value is not None:
        return value
    env_value = os.environ.get(env_name)
    if env_value is None:
        return None
    env_value = env_value.strip()
    return env_value or None


def _normalize_failure_reason(success: bool, failure_reason: str | None) -> str:
    if failure_reason is None:
        if success:
            return "none"
        raise ValidationError("failure_reason is required when success is false")
    reason = str(failure_reason).strip()
    if not reason:
        if success:
            return "none"
        raise ValidationError("failure_reason is required when success is false")
    return reason


def build_record_from_args(args: argparse.Namespace) -> dict[str, Any]:
    metric_type = str(args.metric_type or "").strip().lower()
    if not metric_type:
        raise ValidationError("metric_type must be set")

    record: dict[str, Any] = {
        "schema_version": AUTOPILOT_METRICS_SCHEMA_VERSION,
        "metric_type": metric_type,
        "issue_number": _coerce_int(args.issue_number, "issue_number"),
        "timestamp": args.timestamp or _utc_now_iso(),
        "cycle_count": _coerce_int(args.cycle_count, "cycle_count"),
    }

    if metric_type == "step":
        if args.step_name is None:
            raise ValidationError("step_name is required")
        started_at = _env_or_value(args.started_at, "AUTOPILOT_STEP_STARTED_AT")
        ended_at = _env_or_value(args.ended_at, "AUTOPILOT_STEP_ENDED_AT")
        started_at_ms = _env_or_value(args.started_at_ms, "AUTOPILOT_STEP_STARTED_AT_MS")
        ended_at_ms = _env_or_value(args.ended_at_ms, "AUTOPILOT_STEP_ENDED_AT_MS")
        if started_at and started_at_ms:
            raise ValidationError("use only one of started_at or started_at_ms")
        if ended_at and ended_at_ms:
            raise ValidationError("use only one of ended_at or ended_at_ms")
        if started_at_ms and ended_at:
            raise ValidationError("ended_at cannot be used with started_at_ms")
        if started_at and ended_at_ms:
            raise ValidationError("ended_at_ms cannot be used with started_at")
        duration_ms = args.duration_ms
        if duration_ms is None:
            if not started_at and started_at_ms is None:
                raise ValidationError(
                    "duration_ms is required unless started_at or started_at_ms is set"
                )
            if started_at_ms is not None:
                if ended_at_ms is None:
                    ended_at_ms = _utc_now_epoch_ms()
                duration_ms = _duration_ms_from_epoch_bounds(
                    _coerce_int(started_at_ms, "started_at_ms"),
                    _coerce_int(ended_at_ms, "ended_at_ms"),
                )
            else:
                ended_at = ended_at or _utc_now_iso()
                duration_ms = _duration_ms_from_bounds(str(started_at), str(ended_at))
        if args.success is None:
            raise ValidationError("success is required")
        success = _coerce_bool(args.success, "success")
        failure_reason = _env_or_value(args.failure_reason, "AUTOPILOT_FAILURE_REASON")
        record.update(
            {
                "step_name": args.step_name,
                "duration_ms": _coerce_int(duration_ms, "duration_ms"),
                "success": success,
                "failure_reason": _normalize_failure_reason(success, failure_reason),
            }
        )
        return record

    if metric_type == "cycle":
        if args.max_cycles is not None:
            record["max_cycles"] = _coerce_int(args.max_cycles, "max_cycles")
        if args.steps_attempted is not None:
            record["steps_attempted"] = _coerce_int(args.steps_attempted, "steps_attempted")
        if args.steps_completed is not None:
            record["steps_completed"] = _coerce_int(args.steps_completed, "steps_completed")
        return record

    if metric_type == "escalation":
        escalation_reason = _env_or_value(args.escalation_reason, "AUTOPILOT_ESCALATION_REASON")
        if escalation_reason is None or not str(escalation_reason).strip():
            raise ValidationError("escalation_reason must be a non-empty string")
        record["escalation_reason"] = str(escalation_reason).strip()
        return record

    raise ValidationError("metric_type must be 'step', 'cycle', or 'escalation'")


def load_record_from_json(payload: str) -> dict[str, Any]:
    try:
        record = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValidationError("record_json must be valid JSON") from exc
    if not isinstance(record, dict):
        raise ValidationError("record_json must decode to an object")
    if "schema_version" not in record:
        record["schema_version"] = AUTOPILOT_METRICS_SCHEMA_VERSION
    if "timestamp" not in record:
        record["timestamp"] = _utc_now_iso()
    return record


def append_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, separators=(",", ":"), sort_keys=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Append auto-pilot metrics record to NDJSON log.")
    parser.add_argument("--path", default="autopilot-metrics.ndjson", help="NDJSON output path")
    parser.add_argument("--record-json", help="JSON object payload for the record")
    parser.add_argument(
        "--print-schema",
        action="store_true",
        help="Print JSON schema for auto-pilot metrics and exit",
    )
    parser.add_argument(
        "--metric-type", choices=["step", "cycle", "escalation"], help="Record type"
    )
    parser.add_argument("--issue-number", help="Issue number")
    parser.add_argument("--cycle-count", help="Auto-pilot cycle count")
    parser.add_argument("--timestamp", help="ISO 8601 timestamp (defaults to now)")
    parser.add_argument("--step-name", help="Step name for step records")
    parser.add_argument("--duration-ms", help="Step duration in milliseconds")
    parser.add_argument("--started-at", help="ISO 8601 step start timestamp (optional)")
    parser.add_argument("--ended-at", help="ISO 8601 step end timestamp (optional)")
    parser.add_argument("--started-at-ms", help="Epoch milliseconds for step start (optional)")
    parser.add_argument("--ended-at-ms", help="Epoch milliseconds for step end (optional)")
    parser.add_argument("--success", help="Step success flag (true/false)")
    parser.add_argument("--failure-reason", help="Failure reason for step records")
    parser.add_argument("--max-cycles", help="Max cycles for cycle records")
    parser.add_argument("--steps-attempted", help="Steps attempted for cycle records")
    parser.add_argument("--steps-completed", help="Steps completed for cycle records")
    parser.add_argument("--escalation-reason", help="Escalation reason for escalation records")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.print_schema:
            print(schema_payload())
            return 0
        if args.record_json:
            record = load_record_from_json(args.record_json)
        else:
            record = build_record_from_args(args)
        validate_record(record)
        append_record(Path(args.path), record)
    except Exception as exc:
        print(f"autopilot_metrics_collector: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main(sys.argv[1:]))
