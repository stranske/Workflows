#!/usr/bin/env python3
"""Generate shields.io endpoint JSON for workflow metrics badges."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.metrics_badges_config import BADGE_TYPES, BadgeType

_SUCCESS_RATE_OK = 95.0
_SUCCESS_RATE_WARN = 85.0
_AVG_DURATION_WARN_SECONDS = 600.0
_AVG_DURATION_CRITICAL_SECONDS = 900.0

_NUMERIC_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*%?\s*$")
_DURATION_RE = re.compile(
    r"^\s*(-?\d+(?:\.\d+)?)\s*(ms|millisecond|milliseconds|s|sec|secs|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours)?\s*$",
    re.IGNORECASE,
)
_DURATION_SEGMENT_RE = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*(ms|millisecond|milliseconds|s|sec|secs|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BadgePayload:
    label: str
    message: str
    color: str

    def to_endpoint_json(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "label": self.label,
            "message": self.message,
            "color": self.color,
        }


def _extract_metric(metrics: Mapping[str, Any], key: str) -> Any:
    if key in metrics:
        return metrics[key]
    summary = metrics.get("summary")
    if isinstance(summary, Mapping) and key in summary:
        return summary[key]
    return None


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        match = _NUMERIC_RE.match(value)
        if match:
            return float(match.group(1))
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    percent = value * 100 if 0 <= value <= 1 else value
    return f"{percent:.1f}%"


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    total_seconds = int(round(seconds))
    minutes, sec = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes or hours:
        parts.append(f"{minutes}m")
    parts.append(f"{sec}s")
    return " ".join(parts)


def _status_color(status: str) -> str:
    if status in {"success", "ok", "passed"}:
        return "brightgreen"
    if status in {"failure", "failed", "error", "cancelled", "canceled"}:
        return "red"
    if status in {"running", "in_progress", "queued"}:
        return "blue"
    if status in {"skipped", "neutral"}:
        return "lightgrey"
    if status == "n/a":
        return "lightgrey"
    return "yellow"


def _success_rate_color(rate: float | None) -> str:
    if rate is None:
        return "lightgrey"
    percent = rate * 100 if 0 <= rate <= 1 else rate
    if percent >= _SUCCESS_RATE_OK:
        return "brightgreen"
    if percent >= _SUCCESS_RATE_WARN:
        return "yellow"
    return "red"


def _avg_duration_color(seconds: float | None) -> str:
    if seconds is None:
        return "lightgrey"
    if seconds <= _AVG_DURATION_WARN_SECONDS:
        return "brightgreen"
    if seconds <= _AVG_DURATION_CRITICAL_SECONDS:
        return "yellow"
    return "red"


def _build_success_rate(metrics: Mapping[str, Any], badge: BadgeType) -> BadgePayload:
    value = _coerce_float(_extract_metric(metrics, badge.metric_key))
    if value is None:
        for alt_key in ("recent_success_rate", "overall_success_rate", "success_rate_percent"):
            value = _coerce_float(_extract_metric(metrics, alt_key))
            if value is not None:
                break
    return BadgePayload(
        label=badge.label,
        message=_format_percent(value),
        color=_success_rate_color(value),
    )


def _build_avg_duration(metrics: Mapping[str, Any], badge: BadgeType) -> BadgePayload:
    value = _coerce_duration_seconds(_extract_metric(metrics, badge.metric_key))
    if value is None:
        fallback_keys = (
            ("avg_duration", "s"),
            ("average_duration_seconds", "s"),
            ("avg_duration_ms", "ms"),
            ("average_duration_ms", "ms"),
            ("avg_duration_millis", "ms"),
        )
        for alt_key, unit in fallback_keys:
            value = _coerce_duration_seconds(_extract_metric(metrics, alt_key), unit=unit)
            if value is not None:
                break
    return BadgePayload(
        label=badge.label,
        message=_format_duration(value),
        color=_avg_duration_color(value),
    )


def _build_last_run_status(metrics: Mapping[str, Any], badge: BadgeType) -> BadgePayload:
    raw = _extract_metric(metrics, badge.metric_key)
    if raw is None:
        for alt_key in ("last_run_conclusion", "last_run_result", "last_run_state"):
            raw = _extract_metric(metrics, alt_key)
            if raw is not None:
                break
    status = str(raw).strip().lower() if raw else "n/a"
    return BadgePayload(
        label=badge.label,
        message=status.replace("_", " "),
        color=_status_color(status),
    )


def _parse_duration_segments(value: str) -> float | None:
    matches = list(_DURATION_SEGMENT_RE.finditer(value))
    if not matches:
        return None
    remainder = _DURATION_SEGMENT_RE.sub("", value)
    if remainder.strip():
        return None
    total_seconds = 0.0
    for match in matches:
        magnitude = float(match.group(1))
        unit = match.group(2).lower()
        if unit.startswith("ms"):
            total_seconds += magnitude / 1000.0
        elif unit in {"s", "sec", "secs", "second", "seconds"}:
            total_seconds += magnitude
        elif unit in {"m", "min", "mins", "minute", "minutes"}:
            total_seconds += magnitude * 60.0
        else:
            total_seconds += magnitude * 3600.0
    return total_seconds


def _parse_colon_duration(value: str) -> float | None:
    parts = value.split(":")
    if len(parts) not in {2, 3}:
        return None
    try:
        if len(parts) == 2:
            minutes = float(parts[0])
            seconds = float(parts[1])
            return minutes * 60.0 + seconds
        hours = float(parts[0])
        minutes = float(parts[1])
        seconds = float(parts[2])
    except ValueError:
        return None
    return hours * 3600.0 + minutes * 60.0 + seconds


def _coerce_duration_seconds(value: Any, *, unit: str = "s") -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.strip()
        if ":" in value:
            parsed = _parse_colon_duration(value)
            if parsed is not None:
                return parsed
        parsed = _parse_duration_segments(value)
        if parsed is not None:
            return parsed
        match = _DURATION_RE.match(value)
        if not match:
            return None
        value = float(match.group(1))
        unit = (match.group(2) or unit).lower()
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if unit.startswith("ms"):
        return numeric / 1000.0
    return numeric


def build_endpoint_payloads(metrics: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    builders = {
        "success_rate": _build_success_rate,
        "avg_duration": _build_avg_duration,
        "last_run_status": _build_last_run_status,
    }
    for badge in BADGE_TYPES:
        builder = builders.get(badge.name)
        if builder is None:
            continue
        payload = builder(metrics, badge)
        payloads[badge.name] = payload.to_endpoint_json()
    return payloads


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate shields.io endpoint JSON badges.")
    parser.add_argument(
        "--metrics-path",
        default="metrics-summary.json",
        help="Path to metrics JSON input.",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory to write endpoint JSON files (one per badge).",
    )
    parser.add_argument(
        "--badge",
        help="Write a single badge JSON to stdout (use badge name).",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    return parser


def _load_metrics(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("metrics JSON must be an object")
    return parsed


def _write_json(path: Path, payload: dict[str, Any], *, pretty: bool) -> None:
    indent = 2 if pretty else None
    path.write_text(json.dumps(payload, indent=indent, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    metrics_path = Path(args.metrics_path)
    if not metrics_path.exists():
        print(f"metrics file not found: {metrics_path}", file=sys.stderr)
        return 1

    try:
        metrics = _load_metrics(metrics_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"failed to load metrics: {exc}", file=sys.stderr)
        return 1

    payloads = build_endpoint_payloads(metrics)
    if args.badge:
        payload = payloads.get(args.badge)
        if payload is None:
            print(f"unknown badge: {args.badge}", file=sys.stderr)
            return 1
        json_kwargs = {"indent": 2, "sort_keys": True} if args.pretty else {}
        print(json.dumps(payload, **json_kwargs))
        return 0

    if not args.output_dir:
        print("output-dir is required when not using --badge", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        _write_json(output_dir / f"{name}.json", payload, pretty=args.pretty)
    print(f"Wrote {len(payloads)} badge payloads to {output_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main(sys.argv[1:]))
