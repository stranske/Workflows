#!/usr/bin/env python3
"""Retain ``gh run view --json jobs,status,conclusion`` evidence for named Gate jobs.

Issue #4284's live-verification gate names Workflows run 40551187519 and requires
``python ci / python 3.13`` and ``python ci / python 3.14`` to finish within 600
seconds. ``gh run view`` emits camelCase timestamps and an HTML ``url``, which
this module records with the calculated durations.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from scripts.check_gate_python_job_timings import job_duration_seconds, timestamp_text

ISSUE_NUMBER = 4284
DEFAULT_REPO = "stranske/Workflows"
DEFAULT_RUN_ID = 40551187519
DEFAULT_MAX_SECONDS = 600.0
NAMED_JOBS = (
    "python ci / python 3.13",
    "python ci / python 3.14",
)
SCHEMA = "issue-4284-gate-run-view/v1"


def job_page_url(job: Mapping[str, Any]) -> str | None:
    """Return the Actions job HTML URL from REST or ``gh run view`` fields."""
    for key in ("html_url", "htmlUrl", "url"):
        value = job.get(key)
        if isinstance(value, str) and value.startswith("https://"):
            return value
    return None


def _database_id(job: Mapping[str, Any]) -> int | None:
    value = job.get("databaseId", job.get("database_id", job.get("id")))
    if isinstance(value, int):
        return value
    return None


def select_named_jobs(jobs: Any, names: Sequence[str] = NAMED_JOBS) -> dict[str, dict[str, Any]]:
    """Keep the first payload object for each required job name."""
    selected: dict[str, dict[str, Any]] = {}
    if not isinstance(jobs, list):
        return selected
    allowed = set(names)
    for job in jobs:
        if not isinstance(job, dict):
            continue
        name = job.get("name")
        if isinstance(name, str) and name in allowed and name not in selected:
            selected[name] = job
    return selected


def calculated_job(job: Mapping[str, Any], *, max_seconds: float) -> dict[str, Any]:
    """Project one job into the retained duration record."""
    seconds = job_duration_seconds(dict(job))
    status = job.get("status")
    conclusion = job.get("conclusion")
    within_limit = (
        status == "completed"
        and conclusion == "success"
        and seconds is not None
        and seconds <= max_seconds
    )
    return {
        "name": job.get("name"),
        "database_id": _database_id(job),
        "status": status,
        "conclusion": conclusion,
        "started_at": timestamp_text(job, "started_at", "startedAt"),
        "completed_at": timestamp_text(job, "completed_at", "completedAt"),
        "seconds": seconds,
        "url": job_page_url(job),
        "within_limit": within_limit,
    }


def retain_gate_run_view(
    payload: Mapping[str, Any],
    *,
    run_id: int = DEFAULT_RUN_ID,
    repo: str = DEFAULT_REPO,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    job_names: Sequence[str] = NAMED_JOBS,
    command: str | None = None,
) -> dict[str, Any]:
    """Build delivery evidence from a ``gh run view --json jobs,status,conclusion`` payload.

    The embedded ``gh_run_view`` object keeps run status, conclusion, and the
    named jobs as returned by the CLI (including steps). Calculated durations
    are ``completedAt - startedAt`` in seconds.
    """
    if max_seconds <= 0:
        raise ValueError("max_seconds must be positive")
    status = payload.get("status")
    conclusion = payload.get("conclusion")
    selected = select_named_jobs(payload.get("jobs"), job_names)
    calculated = [
        calculated_job(selected[name], max_seconds=max_seconds)
        for name in job_names
        if name in selected
    ]
    failures: list[str] = []
    if status != "completed":
        failures.append(f"run status is {status!r}, expected 'completed'")
    if conclusion != "success":
        failures.append(f"run conclusion is {conclusion!r}, expected 'success'")
    by_name = {row["name"]: row for row in calculated}
    for name in job_names:
        row = by_name.get(name)
        if row is None:
            failures.append(f"missing job {name!r}")
            continue
        if row["status"] != "completed" or row["conclusion"] != "success":
            failures.append(
                f"{name} status={row['status']!r} conclusion={row['conclusion']!r}, "
                "expected completed/success"
            )
        elif row["seconds"] is None:
            failures.append(f"{name} has no duration")
        elif row["seconds"] > max_seconds:
            failures.append(f"{name} took {row['seconds']:.0f}s (limit {max_seconds:.0f}s)")
        if not row["url"]:
            failures.append(f"{name} has no job URL")
    rendered_command = command or (
        f"gh run view {run_id} --repo {repo} --json jobs,status,conclusion"
    )
    return {
        "schema": SCHEMA,
        "issue": ISSUE_NUMBER,
        "repo": repo,
        "run_id": run_id,
        "run_url": f"https://github.com/{repo}/actions/runs/{run_id}",
        "command": rendered_command,
        "max_seconds": max_seconds,
        "passed": not failures,
        "failures": failures,
        "gh_run_view": {
            "status": status,
            "conclusion": conclusion,
            "jobs": [selected[name] for name in job_names if name in selected],
        },
        "jobs": calculated,
    }


def evidence_json(evidence: Mapping[str, Any]) -> str:
    """Serialize retained evidence with a trailing newline."""
    return json.dumps(evidence, indent=2) + "\n"


def load_evidence(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return payload


def recalculated_matches(evidence: Mapping[str, Any]) -> bool:
    """Recompute durations from the embedded CLI slice and compare the record."""
    embedded = evidence.get("gh_run_view")
    if not isinstance(embedded, dict):
        return False
    fresh = retain_gate_run_view(
        embedded,
        run_id=int(evidence["run_id"]),
        repo=str(evidence["repo"]),
        max_seconds=float(evidence["max_seconds"]),
        command=str(evidence.get("command") or ""),
    )
    return (
        fresh["passed"] == evidence.get("passed")
        and fresh["failures"] == evidence.get("failures")
        and fresh["jobs"] == evidence.get("jobs")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="gh run view JSON file")
    parser.add_argument("--output", type=Path, required=True, help="Evidence JSON to write")
    parser.add_argument("--run-id", type=int, default=DEFAULT_RUN_ID)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--max-seconds", type=float, default=DEFAULT_MAX_SECONDS)
    args = parser.parse_args(argv)
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print("gh run view payload must be a JSON object", file=sys.stderr)
        return 1
    evidence = retain_gate_run_view(
        payload,
        run_id=args.run_id,
        repo=args.repo,
        max_seconds=args.max_seconds,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(evidence_json(evidence), encoding="utf-8")
    for job in evidence["jobs"]:
        print(
            f"{job['name']}={job['seconds']}s url={job['url']} within_limit={job['within_limit']}"
        )
    if evidence["passed"]:
        print(
            f"PASS: run {args.run_id} conclusion=success and "
            f"{', '.join(NAMED_JOBS)} each <= {args.max_seconds:.0f}s"
        )
        return 0
    print("FAIL: retained Gate run does not meet the #4284 job limit", file=sys.stderr)
    for failure in evidence["failures"]:
        print(f"  - {failure}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
