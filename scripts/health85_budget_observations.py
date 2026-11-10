#!/usr/bin/env python3
"""Retain Health 85 trailing-seven-day Gate p50 observations for issue #4284.

Health 85 is ``health-85-ci-time-budget.yml``. Its published report stores p50
in minutes. Issue #4284's sustained gate compares those daily values with 600
seconds and stays incomplete when a day is missing or over the limit.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

HEALTH85_NAME_PREFIX = "Health 85"
HEALTH85_PATH = ".github/workflows/health-85-ci-time-budget.yml"
DEFAULT_REPO = "stranske/Workflows"
DEFAULT_MAX_SECONDS = 600.0
TARGET_MINUTES = 10.0
SCHEMA = "issue-4284-health85-observations/v1"
RUN_URL = "https://github.com/stranske/Workflows/actions/runs/{run_id}"


def find_health85(workflows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return the single workflow whose name starts with ``Health 85``."""
    matches = [
        row
        for row in workflows
        if isinstance(row, Mapping) and str(row.get("name") or "").startswith(HEALTH85_NAME_PREFIX)
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one Health 85 workflow, found {len(matches)}")
    row = matches[0]
    path = str(row.get("path") or "")
    if path != HEALTH85_PATH:
        raise ValueError(f"Health 85 path is {path!r}, expected {HEALTH85_PATH!r}")
    workflow_id = row.get("id")
    if not isinstance(workflow_id, int):
        raise ValueError("Health 85 workflow id must be an int")
    return {
        "id": workflow_id,
        "name": str(row["name"]),
        "path": path,
        "state": row.get("state"),
    }


def _as_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid observation date: {value!r}") from exc


def _p50_minutes(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"p50_minutes must be a number or null, got {value!r}")
    return float(value)


def build_observations(
    rows: Sequence[Mapping[str, Any]],
    *,
    repo: str = DEFAULT_REPO,
    max_seconds: float = DEFAULT_MAX_SECONDS,
) -> dict[str, Any]:
    """Evaluate consecutive daily p50 rows against the 600-second gate.

    Each row needs ``date`` (``YYYY-MM-DD``), ``p50_minutes`` (number or null),
    and ``run_id``. Null p50 values are retained as missing measurements.
    """
    if max_seconds <= 0:
        raise ValueError("max_seconds must be positive")
    if not rows:
        raise ValueError("observations must be non-empty")
    evaluated: list[dict[str, Any]] = []
    failures: list[str] = []
    for row in rows:
        day = _as_date(str(row.get("date") or ""))
        minutes = _p50_minutes(row.get("p50_minutes"))
        run_id = row.get("run_id")
        if not isinstance(run_id, int):
            raise ValueError(f"{day.isoformat()} run_id must be an int")
        seconds = None if minutes is None else round(minutes * 60.0, 1)
        within = seconds is not None and seconds <= max_seconds
        status = "measured" if minutes is not None else "measurement_unavailable"
        note = row.get("note")
        evaluated.append(
            {
                "date": day.isoformat(),
                "units": "minutes",
                "p50_minutes": minutes,
                "p50_seconds": seconds,
                "within_600_seconds": within,
                "status": status,
                "run_id": run_id,
                "run_conclusion": row.get("run_conclusion"),
                "source_run_url": RUN_URL.format(run_id=run_id),
                "note": note if isinstance(note, str) and note else None,
            }
        )
        if minutes is None:
            failures.append(f"{day.isoformat()}: p50 missing ({status})")
        elif not within:
            failures.append(
                f"{day.isoformat()}: p50 {seconds:.1f}s exceeds {max_seconds:.0f}s "
                f"({minutes:.4f} min)"
            )
    dates = [_as_date(row["date"]) for row in evaluated]
    if dates != sorted(dates):
        failures.append("observation dates are not sorted")
    consecutive = all(
        later - earlier == timedelta(days=1)
        for earlier, later in zip(dates, dates[1:], strict=False)
    )
    if not consecutive:
        failures.append("observation dates are not consecutive calendar days")
    if len(evaluated) != 7:
        failures.append(f"expected 7 daily observations, found {len(evaluated)}")
    return {
        "repo": repo,
        "target_minutes": TARGET_MINUTES,
        "max_seconds": max_seconds,
        "consecutive_calendar_dates": consecutive and dates == sorted(dates),
        "qualifying_seven_day_series": not failures,
        "failures": failures,
        "p50_series_minutes": {row["date"]: row["p50_minutes"] for row in evaluated},
        "observations": evaluated,
    }


def build_report(
    workflows: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    *,
    report_branch: str,
    report_blob_sha: str,
    repo: str = DEFAULT_REPO,
    issue: int = 4284,
    schema: str | None = None,
) -> dict[str, Any]:
    """Combine the Health 85 identity with evaluated daily observations."""
    workflow = find_health85(workflows)
    series = build_observations(rows, repo=repo)
    resolved_schema = schema or (
        SCHEMA if issue == 4284 else f"issue-{issue}-health85-observations/v1"
    )
    return {
        "schema": resolved_schema,
        "issue": issue,
        "source": {
            "workflow": workflow,
            "report_repo": repo,
            "report_branch": report_branch,
            "report_path": "docs/reports/ci-budget.json",
            "report_blob_sha": report_blob_sha,
            "p50_units": "minutes",
            "gate_units": "seconds",
        },
        **series,
    }


def report_json(report: Mapping[str, Any]) -> str:
    return json.dumps(report, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflows", type=Path, required=True, help="gh workflow list JSON")
    parser.add_argument("--observations", type=Path, required=True, help="Daily p50 JSON array")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report-branch", default="ci-time-budget")
    parser.add_argument("--report-blob-sha", required=True)
    parser.add_argument("--issue", type=int, default=4284)
    args = parser.parse_args(argv)
    workflows = json.loads(args.workflows.read_text(encoding="utf-8"))
    rows = json.loads(args.observations.read_text(encoding="utf-8"))
    if not isinstance(workflows, list) or not isinstance(rows, list):
        print("workflows and observations must be JSON arrays", file=sys.stderr)
        return 1
    report = build_report(
        workflows,
        rows,
        report_branch=args.report_branch,
        report_blob_sha=args.report_blob_sha,
        issue=args.issue,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report_json(report), encoding="utf-8")
    print(
        f"Health 85 id={report['source']['workflow']['id']} "
        f"qualifying_seven_day_series={report['qualifying_seven_day_series']}"
    )
    for failure in report["failures"]:
        print(f"  - {failure}")
    return 0 if report["qualifying_seven_day_series"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
