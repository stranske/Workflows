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
"""

from __future__ import annotations

import argparse
import json
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
            "required": ("metric_type", "issue_number", "timestamp", "cycle_count"),
            "optional": ("max_cycles", "steps_attempted", "steps_completed"),
        },
        "escalation": {
            "required": (
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


def _validate_step(record: dict[str, Any]) -> None:
    missing = [field for field in STEP_REQUIRED_FIELDS if field not in record]
    if missing:
        raise ValidationError(f"missing fields: {', '.join(missing)}")

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Append auto-pilot metrics record to NDJSON log.")
    parser.add_argument("--path", default="autopilot-metrics.ndjson", help="NDJSON output path")
    parser.add_argument("--record-json", required=True, help="JSON object payload for the record")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        record = load_record_from_json(args.record_json)
        validate_record(record)
        append_record(Path(args.path), record)
    except Exception as exc:
        print(f"autopilot_metrics_collector: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main(sys.argv[1:]))
