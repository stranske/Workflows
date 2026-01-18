#!/usr/bin/env python
"""Compute coverage delta against a baseline for CI reporting."""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

_DEFAULT_COVERAGE_XML = "coverage.xml"
_DEFAULT_OUTPUT = "coverage-delta.json"
_DEFAULT_BASELINE = 0.0
_DEFAULT_ALERT_DROP = 1.0


def _parse_float(value: str | None, env_name: str, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError as exc:  # pragma: no cover - defensive
        raise SystemExit(f"Invalid float for {env_name}: {value!r}") from exc


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "on"}


def _extract_line_rate(xml_path: Path) -> float:
    if not xml_path.is_file():
        raise FileNotFoundError(f"Coverage XML not found: {xml_path}")
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError as exc:  # pragma: no cover - malformed coverage report is rare
        raise SystemExit(f"Failed to parse coverage XML {xml_path}: {exc}") from exc
    raw = root.attrib.get("line-rate")
    if raw is None:
        raise SystemExit(f"Coverage XML {xml_path} missing line-rate attribute")
    try:
        return float(raw) * 100.0
    except ValueError as exc:  # pragma: no cover - defensive
        raise SystemExit(f"Invalid line-rate value in coverage XML: {raw!r}") from exc


def _build_payload(
    current: float,
    baseline: float,
    alert_drop: float,
    *,
    fail_on_drop: bool,
) -> tuple[dict[str, Any], bool]:
    timestamp = _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    drop = max(0.0, baseline - current) if baseline > 0 else 0.0
    delta = current - baseline
    status: str
    should_fail = False

    if baseline <= 0:
        status = "no-baseline"
    elif drop == 0:
        status = "ok"
    elif drop >= alert_drop:
        status = "fail" if fail_on_drop else "alert"
        should_fail = status == "fail"
    else:
        status = "ok"

    payload = {
        "timestamp": timestamp,
        "current": round(current, 4),
        "baseline": round(baseline, 4),
        "delta": round(delta, 4),
        "drop": round(drop, 4),
        "threshold": alert_drop,
        "status": status,
        "fail_on_drop": fail_on_drop,
    }
    return payload, should_fail


def main() -> int:
    xml_path = Path(os.environ.get("COVERAGE_XML_PATH", _DEFAULT_COVERAGE_XML))
    output_path = Path(os.environ.get("OUTPUT_PATH", _DEFAULT_OUTPUT))
    baseline = _parse_float(
        os.environ.get("BASELINE_COVERAGE"), "BASELINE_COVERAGE", _DEFAULT_BASELINE
    )
    alert_drop = _parse_float(os.environ.get("ALERT_DROP"), "ALERT_DROP", _DEFAULT_ALERT_DROP)
    fail_on_drop = _truthy(os.environ.get("FAIL_ON_DROP"))

    try:
        current = _extract_line_rate(xml_path)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    payload, should_fail = _build_payload(current, baseline, alert_drop, fail_on_drop=fail_on_drop)

    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Coverage delta written to {output_path}")

    return 1 if should_fail else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
