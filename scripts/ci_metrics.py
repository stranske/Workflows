#!/usr/bin/env python
"""Extract pytest metrics from JUnit XML.

This helper is invoked by the reusable CI workflow.  It consumes the JUnit
report emitted by pytest, summarises aggregate counts, captures failure and
error details, and records the slowest tests above a configurable threshold.

Environment variables (all optional):
    JUNIT_PATH      Path to the JUnit XML file (default: ``pytest-junit.xml``)
    OUTPUT_PATH     Destination JSON file (default: ``ci-metrics.json``)
    TOP_N           Maximum number of slow tests to record (default: ``15``)
    MIN_SECONDS     Minimum duration (inclusive) for the slow test list.

The resulting JSON structure intentionally mirrors the data consumed by the
Phase-2 CI dashboards (see ``docs/ci-workflow.md``).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

_DEFAULT_JUNIT = "pytest-junit.xml"
_DEFAULT_OUTPUT = "ci-metrics.json"
_DEFAULT_TOP_N = 15
_DEFAULT_MIN_SECONDS = 1.0


def _tag_name(node: ET.Element) -> str:
    """Return the local tag name (strip XML namespaces)."""
    tag = node.tag
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _parse_int(value: str | None, env_name: str, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except ValueError as exc:  # pragma: no cover - defensive
        raise SystemExit(f"Invalid integer for {env_name}: {value!r}") from exc
    if parsed < 0:
        raise SystemExit(f"{env_name} must be non-negative (got {parsed})")
    return parsed


def _parse_float(value: str | None, env_name: str, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        parsed = float(value)
    except ValueError as exc:  # pragma: no cover - defensive
        raise SystemExit(f"Invalid float for {env_name}: {value!r}") from exc
    if parsed < 0:
        raise SystemExit(f"{env_name} must be non-negative (got {parsed})")
    return parsed


@dataclass(frozen=True)
class _TestCase:
    name: str
    classname: str
    nodeid: str
    time: float
    outcome: str  # passed | failure | error | skipped
    message: str | None
    error_type: str | None
    details: str | None


def _build_nodeid(classname: str, name: str) -> str:
    if classname and name:
        return f"{classname}::{name}"
    return name or classname or "(unknown)"


def _extract_testcases(root: ET.Element) -> list[_TestCase]:
    cases: list[_TestCase] = []
    for testcase in root.findall(".//testcase"):
        name = testcase.attrib.get("name", "")
        classname = testcase.attrib.get("classname", "")
        nodeid = _build_nodeid(classname, name)
        try:
            duration = float(testcase.attrib.get("time", "0") or 0.0)
        except ValueError:
            duration = 0.0

        outcome = "passed"
        message: str | None = None
        err_type: str | None = None
        details: str | None = None

        for child in testcase:
            tag = _tag_name(child).lower()
            if tag in {"failure", "error", "skipped"}:
                outcome = "error" if tag == "error" else tag
                message = child.attrib.get("message") if child.attrib else None
                err_type = child.attrib.get("type") if child.attrib else None
                text = child.text or ""
                details = text.strip() or None
                # First terminal status wins – ignore subsequent system-out/in
                break

        cases.append(
            _TestCase(
                name=name,
                classname=classname,
                nodeid=nodeid,
                time=duration,
                outcome=outcome,
                message=message,
                error_type=err_type,
                details=details,
            )
        )
    return cases


def _summarise(cases: Sequence[_TestCase]) -> dict[str, Any]:
    tests = len(cases)
    failures = sum(1 for c in cases if c.outcome == "failure")
    errors = sum(1 for c in cases if c.outcome == "error")
    skipped = sum(1 for c in cases if c.outcome == "skipped")
    passed = tests - failures - errors - skipped
    duration = sum(c.time for c in cases)
    return {
        "tests": tests,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "passed": passed,
        "duration_seconds": round(duration, 6),
    }


def _collect_failures(cases: Iterable[_TestCase]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        if case.outcome not in {"failure", "error"}:
            continue
        rows.append(
            {
                "status": case.outcome,
                "name": case.name,
                "classname": case.classname,
                "nodeid": case.nodeid,
                "time": round(case.time, 6),
                "message": case.message,
                "type": case.error_type,
                "details": case.details,
            }
        )
    return rows


def _collect_slow_tests(
    cases: Sequence[_TestCase],
    *,
    top_n: int,
    min_seconds: float,
) -> list[dict[str, Any]]:
    if not cases or top_n == 0:
        return []
    eligible = [c for c in cases if c.time >= min_seconds]
    eligible.sort(key=lambda c: (-c.time, c.nodeid))
    subset = eligible[:top_n]
    return [
        {
            "name": c.name,
            "classname": c.classname,
            "nodeid": c.nodeid,
            "time": round(c.time, 6),
            "outcome": c.outcome,
        }
        for c in subset
    ]


def build_metrics(
    junit_path: Path,
    *,
    top_n: int = _DEFAULT_TOP_N,
    min_seconds: float = _DEFAULT_MIN_SECONDS,
) -> dict[str, Any]:
    if not junit_path.is_file():
        raise FileNotFoundError(f"JUnit report not found: {junit_path}")

    try:
        root = ET.parse(junit_path).getroot()
    except ET.ParseError as exc:  # pragma: no cover - JUnit corruption is unlikely
        raise SystemExit(f"Failed to parse JUnit XML {junit_path}: {exc}") from exc

    cases = _extract_testcases(root)
    summary = _summarise(cases)
    failures = _collect_failures(cases)
    slow_tests = _collect_slow_tests(cases, top_n=top_n, min_seconds=min_seconds)

    payload: dict[str, Any] = {
        "generated_at": (
            _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        ),
        "junit_path": str(junit_path),
        "summary": summary,
        "failures": failures,
        "slow_tests": {
            "threshold_seconds": min_seconds,
            "limit": top_n,
            "items": slow_tests,
        },
    }
    return payload


def main() -> int:
    junit_path = Path(os.environ.get("JUNIT_PATH", _DEFAULT_JUNIT))
    output_path = Path(os.environ.get("OUTPUT_PATH", _DEFAULT_OUTPUT))
    top_n = _parse_int(os.environ.get("TOP_N"), "TOP_N", _DEFAULT_TOP_N)
    min_seconds = _parse_float(os.environ.get("MIN_SECONDS"), "MIN_SECONDS", _DEFAULT_MIN_SECONDS)

    try:
        payload = build_metrics(junit_path, top_n=top_n, min_seconds=min_seconds)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Metrics written to {output_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via tests importing main
    sys.exit(main())
