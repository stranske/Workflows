#!/usr/bin/env python
"""Append CI metrics history and optional failure classification.

This helper is executed by the reusable CI workflow after pytest completes.
It records a single NDJSON line containing aggregate test statistics and, when
available, the richer metrics payload.  When classification is enabled it also
emits a companion ``classification.json`` summarising failing / erroring tests.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:  # ``scripts`` is treated as a namespace package during test runs.
    from scripts import ci_metrics
except ModuleNotFoundError:  # pragma: no cover - defensive when executed as script
    import ci_metrics  # type: ignore

_DEFAULT_JUNIT = "pytest-junit.xml"
_DEFAULT_METRICS = "ci-metrics.json"
_DEFAULT_HISTORY = "metrics-history.ndjson"
_DEFAULT_CLASSIFICATION = "classification.json"


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "on"}


def _load_metrics(junit_path: Path, metrics_path: Path) -> tuple[dict[str, Any], bool]:
    if metrics_path.is_file():
        try:
            data = json.loads(metrics_path.read_text(encoding="utf-8"))
            # Basic sanity check
            if isinstance(data, dict) and "summary" in data:
                return data, True
        except json.JSONDecodeError:
            pass  # fall back to regenerating
    # Rebuild metrics from JUnit directly
    data = ci_metrics.build_metrics(junit_path)
    return data, False


def _build_history_record(
    metrics: dict[str, Any],
    *,
    junit_path: Path,
    metrics_path: Path,
    metrics_from_file: bool,
) -> dict[str, Any]:
    timestamp = _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    summary = metrics.get("summary", {})
    failures = metrics.get("failures", [])

    record: dict[str, Any] = {
        "timestamp": timestamp,
        "summary": summary,
        "failures": failures,
        "junit_path": str(junit_path),
    }
    if metrics_from_file:
        record["metrics_path"] = str(metrics_path)
    github_meta = {
        key.lower(): os.environ[key]
        for key in ("GITHUB_RUN_ID", "GITHUB_RUN_NUMBER", "GITHUB_SHA", "GITHUB_REF")
        if os.environ.get(key)
    }
    if github_meta:
        record["github"] = github_meta
    slow_tests = metrics.get("slow_tests")
    if slow_tests:
        record["slow_tests"] = slow_tests
    return record


def _build_classification_payload(metrics: dict[str, Any]) -> dict[str, Any]:
    timestamp = _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    failures = metrics.get("failures", []) or []
    counts = Counter(entry.get("status", "unknown") for entry in failures)
    payload: dict[str, Any] = {
        "timestamp": timestamp,
        "total": sum(counts.values()),
        "counts": dict(counts),
        "entries": [
            {
                "status": entry.get("status"),
                "nodeid": entry.get("nodeid"),
                "message": entry.get("message"),
                "type": entry.get("type"),
                "time": entry.get("time"),
            }
            for entry in failures
        ],
    }
    return payload


def main() -> int:
    junit_path = Path(os.environ.get("JUNIT_PATH", _DEFAULT_JUNIT))
    metrics_path = Path(os.environ.get("METRICS_PATH", _DEFAULT_METRICS))
    history_path = Path(os.environ.get("HISTORY_PATH", _DEFAULT_HISTORY))
    classification_env = os.environ.get("ENABLE_CLASSIFICATION")
    if classification_env is None:
        classification_env = os.environ.get("ENABLE_CLASSIFICATION_FLAG")
    classification_flag = _truthy(classification_env)
    classification_out = Path(os.environ.get("CLASSIFICATION_OUT", _DEFAULT_CLASSIFICATION))

    if not junit_path.is_file():
        print(f"JUnit report not found: {junit_path}", file=sys.stderr)
        return 1

    try:
        metrics, from_file = _load_metrics(junit_path, metrics_path)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    record = _build_history_record(
        metrics,
        junit_path=junit_path,
        metrics_path=metrics_path,
        metrics_from_file=from_file,
    )

    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    print(f"History appended to {history_path}")

    if classification_flag:
        payload = _build_classification_payload(metrics)
        classification_out.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"Classification written to {classification_out}")
    else:
        if classification_out.exists():
            classification_out.unlink()

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
