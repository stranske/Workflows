#!/usr/bin/env python3
"""Append structured auto-pilot metrics records to an NDJSON log."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ValidationError(Exception):
    """Raised when a record fails schema validation."""

    message: str

    def __str__(self) -> str:
        return self.message


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
        append_record(Path(args.path), record)
    except Exception as exc:
        print(f"autopilot_metrics_collector: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main(sys.argv[1:]))
