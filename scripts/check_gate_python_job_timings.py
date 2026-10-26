#!/usr/bin/env python3
"""Assert Hosted Gate python jobs stay within the single-runtime timing policy.

Issue #4260 acceptance: across the N latest successful Workflows Gate pull_request
runs, ``python ci / python 3.13`` and ``python ci / python 3.14`` must each finish
in at most ``max-seconds`` (default 600 = 10 minutes).

Reports also include the Pytest step wall-clock when GitHub job steps are present,
so Hosted confirmation can separate suite time from setup overhead. Optional
``--created-after`` bounds the successful-PR window for dated acceptance reads
(e.g. 2026-11-15).

Pure evaluation helpers are unit-tested; live GitHub reads go through the shared
api_client wrapper (via workflow_startup_failure_diagnostic._gh_api).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.workflow_startup_failure_diagnostic import _gh_api  # noqa: E402

DEFAULT_REPO = "stranske/Workflows"
DEFAULT_WORKFLOW = "pr-00-gate.yml"
DEFAULT_EVENT = "pull_request"
DEFAULT_RUN_LIMIT = 5
DEFAULT_MAX_SECONDS = 600  # 10 minutes
TARGET_JOB_NAMES = (
    "python ci / python 3.13",
    "python ci / python 3.14",
)
PYTEST_STEP_PREFIX = "Pytest (unit tests"

JsonGetter = Callable[[str, str], dict[str, Any]]


@dataclass(frozen=True)
class JobTiming:
    """Wall-clock job duration plus optional Pytest step duration."""

    job_seconds: float
    pytest_step_seconds: float | None = None


def _github_token() -> str:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    return subprocess.check_output(["gh", "auth", "token"], text=True).strip()


def parse_github_timestamp(value: str | None) -> datetime | None:
    """Parse a GitHub Actions ISO-8601 timestamp into an aware datetime."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_created_after(value: str) -> datetime:
    """Parse ``YYYY-MM-DD`` or an ISO-8601 timestamp into an aware UTC datetime."""
    text = value.strip()
    if not text:
        raise ValueError("created-after must be a non-empty date or timestamp")
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        try:
            day = date.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"Invalid created-after date: {value!r}") from exc
        return datetime(day.year, day.month, day.day, tzinfo=UTC)
    parsed = parse_github_timestamp(text)
    if parsed is None:
        raise ValueError(f"Invalid created-after timestamp: {value!r}")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def job_duration_seconds(job: dict[str, Any]) -> float | None:
    """Return wall-clock seconds for a completed job, or None if timestamps missing."""
    started = parse_github_timestamp(job.get("started_at") if isinstance(job, dict) else None)
    completed = parse_github_timestamp(job.get("completed_at") if isinstance(job, dict) else None)
    if started is None or completed is None:
        return None
    seconds = (completed - started).total_seconds()
    if seconds < 0:
        return None
    return seconds


def pytest_step_duration_seconds(job: dict[str, Any]) -> float | None:
    """Return wall-clock seconds for the Gate Pytest step when step timestamps exist."""
    if not isinstance(job, dict):
        return None
    steps = job.get("steps")
    if not isinstance(steps, list):
        return None
    for step in steps:
        if not isinstance(step, dict):
            continue
        name = str(step.get("name") or "")
        if not name.startswith(PYTEST_STEP_PREFIX):
            continue
        return job_duration_seconds(step)
    return None


def extract_python_job_timings(jobs: list[Any]) -> dict[str, JobTiming]:
    """Map target python job names to job + Pytest step timings."""
    timings: dict[str, JobTiming] = {}
    for job in jobs:
        if not isinstance(job, dict):
            continue
        name = str(job.get("name") or "")
        if name not in TARGET_JOB_NAMES:
            continue
        duration = job_duration_seconds(job)
        if duration is None:
            continue
        timings[name] = JobTiming(
            job_seconds=duration,
            pytest_step_seconds=pytest_step_duration_seconds(job),
        )
    return timings


def extract_python_job_durations(jobs: list[Any]) -> dict[str, float]:
    """Map target python job names to durations found in a jobs payload."""
    return {name: timing.job_seconds for name, timing in extract_python_job_timings(jobs).items()}


def durations_from_timings(timings: Mapping[str, JobTiming]) -> dict[str, float]:
    """Project ``JobTiming`` maps down to job-only seconds for policy evaluation."""
    return {name: timing.job_seconds for name, timing in timings.items()}


def evaluate_run_timings(
    run_id: int | str,
    durations: dict[str, float],
    *,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    required_jobs: tuple[str, ...] = TARGET_JOB_NAMES,
) -> list[str]:
    """Return human-readable policy failures for one Gate run (empty = pass)."""
    failures: list[str] = []
    for name in required_jobs:
        if name not in durations:
            failures.append(f"run {run_id}: missing job {name!r}")
            continue
        seconds = durations[name]
        if seconds > max_seconds:
            failures.append(
                f"run {run_id}: {name} took {seconds:.0f}s " f"(limit {max_seconds:.0f}s)"
            )
    return failures


def evaluate_policy(
    run_durations: list[tuple[int | str, dict[str, float]]],
    *,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    required_jobs: tuple[str, ...] = TARGET_JOB_NAMES,
) -> tuple[bool, list[str]]:
    """True when every run's required python jobs are within ``max_seconds``."""
    failures: list[str] = []
    for run_id, durations in run_durations:
        failures.extend(
            evaluate_run_timings(
                run_id,
                durations,
                max_seconds=max_seconds,
                required_jobs=required_jobs,
            )
        )
    return not failures, failures


def list_successful_pr_runs(
    *,
    repo: str,
    workflow: str,
    limit: int,
    token: str,
    get_json: JsonGetter | None = None,
    event: str = DEFAULT_EVENT,
    created_after: datetime | None = None,
) -> list[dict[str, Any]]:
    """Newest successful workflow runs for ``event``, newest first, capped at ``limit``."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    fetch = get_json or _gh_api
    path = (
        f"repos/{repo}/actions/workflows/{workflow}/runs"
        f"?event={event}&status=success&per_page={max(limit * 2, 20)}"
    )
    payload = fetch(path, token)
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise ValueError(f"Unexpected workflow runs payload for {workflow}")
    floor = None
    if created_after is not None:
        floor = (
            created_after if created_after.tzinfo is not None else created_after.replace(tzinfo=UTC)
        )
        floor = floor.astimezone(UTC)
    selected: list[dict[str, Any]] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        if str(run.get("conclusion") or "") != "success":
            continue
        if floor is not None:
            created = parse_github_timestamp(run.get("created_at"))
            if created is None:
                continue
            if created.astimezone(UTC) < floor:
                continue
        selected.append(run)
        if len(selected) >= limit:
            break
    return selected


def collect_run_python_timings(
    *,
    repo: str,
    run_id: int | str,
    token: str,
    get_json: JsonGetter | None = None,
) -> dict[str, JobTiming]:
    """Fetch jobs for one run and return target python job timings."""
    fetch = get_json or _gh_api
    payload = fetch(f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100", token)
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError(f"Unexpected jobs payload for run {run_id}")
    return extract_python_job_timings(jobs)


def collect_run_python_durations(
    *,
    repo: str,
    run_id: int | str,
    token: str,
    get_json: JsonGetter | None = None,
) -> dict[str, float]:
    """Fetch jobs for one run and return target python job durations."""
    return durations_from_timings(
        collect_run_python_timings(repo=repo, run_id=run_id, token=token, get_json=get_json)
    )


def collect_policy_sample(
    *,
    repo: str = DEFAULT_REPO,
    workflow: str = DEFAULT_WORKFLOW,
    limit: int = DEFAULT_RUN_LIMIT,
    token: str | None = None,
    get_json: JsonGetter | None = None,
    created_after: datetime | None = None,
) -> list[tuple[int | str, dict[str, JobTiming]]]:
    """Build (run_id, timings) pairs for the policy sample window."""
    auth = token or _github_token()
    fetch = get_json or _gh_api
    runs = list_successful_pr_runs(
        repo=repo,
        workflow=workflow,
        limit=limit,
        token=auth,
        get_json=fetch,
        created_after=created_after,
    )
    sample: list[tuple[int | str, dict[str, JobTiming]]] = []
    for run in runs:
        run_id = run.get("id")
        if run_id is None:
            continue
        timings = collect_run_python_timings(repo=repo, run_id=run_id, token=auth, get_json=fetch)
        sample.append((run_id, timings))
    return sample


def build_report(
    sample: list[tuple[int | str, dict[str, JobTiming]]],
    *,
    max_seconds: float,
    passed: bool,
    failures: list[str],
    sample_mode: str = "successful_pr_window",
    created_after: str | None = None,
) -> dict[str, Any]:
    """Machine-readable report for evidence / Nov 15 acceptance reads."""
    policy: dict[str, Any] = {
        "max_seconds": max_seconds,
        "required_jobs": list(TARGET_JOB_NAMES),
        "run_count": len(sample),
        "sample_mode": sample_mode,
    }
    if created_after is not None:
        policy["created_after"] = created_after
    return {
        "policy": policy,
        "passed": passed,
        "failures": failures,
        "runs": [
            {
                "run_id": run_id,
                "jobs": {
                    name: {
                        "seconds": timing.job_seconds,
                        "pytest_step_seconds": timing.pytest_step_seconds,
                        "within_policy": timing.job_seconds <= max_seconds,
                    }
                    for name, timing in sorted(timings.items())
                },
            }
            for run_id, timings in sample
        ],
    }


def collect_run_ids_sample(
    *,
    repo: str,
    run_ids: list[int | str],
    token: str | None = None,
    get_json: JsonGetter | None = None,
) -> list[tuple[int | str, dict[str, JobTiming]]]:
    """Build (run_id, timings) pairs for explicit Gate run ids (any conclusion)."""
    if not run_ids:
        raise ValueError("run_ids must be non-empty")
    auth = token or _github_token()
    fetch = get_json or _gh_api
    sample: list[tuple[int | str, dict[str, JobTiming]]] = []
    for run_id in run_ids:
        timings = collect_run_python_timings(repo=repo, run_id=run_id, token=auth, get_json=fetch)
        sample.append((run_id, timings))
    return sample


def _format_run_line(run_id: int | str, timings: Mapping[str, JobTiming]) -> str:
    parts: list[str] = []
    for name, timing in sorted(timings.items()):
        part = f"{name}={timing.job_seconds:.0f}s"
        if timing.pytest_step_seconds is not None:
            part += f" (pytest={timing.pytest_step_seconds:.0f}s)"
        parts.append(part)
    return f"run {run_id}: " + (", ".join(parts) if parts else "no target jobs")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check that Workflows Gate python 3.13/3.14 jobs stay within the "
            "single-runtime coverage timing policy across recent successful PR runs."
        )
    )
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    parser.add_argument("--limit", type=int, default=DEFAULT_RUN_LIMIT)
    parser.add_argument("--max-seconds", type=float, default=DEFAULT_MAX_SECONDS)
    parser.add_argument(
        "--created-after",
        default=None,
        help=(
            "Only include successful PR runs created at/after this UTC date "
            "(YYYY-MM-DD) or ISO-8601 timestamp. Use for dated acceptance reads "
            "such as 2026-11-15."
        ),
    )
    parser.add_argument(
        "--run-id",
        action="append",
        dest="run_ids",
        default=None,
        help=(
            "Evaluate specific Gate run id(s) instead of the latest successful "
            "PR window (repeatable). Useful for pre-merge PR-head reads when the "
            "overall Gate conclusion failed for unrelated reasons."
        ),
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write the machine-readable timing report",
    )
    args = parser.parse_args(argv)

    created_after = parse_created_after(args.created_after) if args.created_after else None

    if args.run_ids:
        sample = collect_run_ids_sample(repo=args.repo, run_ids=list(args.run_ids))
        sample_mode = "explicit_run_ids"
    else:
        sample = collect_policy_sample(
            repo=args.repo,
            workflow=args.workflow,
            limit=args.limit,
            created_after=created_after,
        )
        sample_mode = "successful_pr_window"
        if len(sample) < args.limit:
            bound = f" created at/after {args.created_after}" if args.created_after else ""
            print(
                f"Only found {len(sample)} successful {DEFAULT_EVENT} runs{bound} "
                f"(needed {args.limit})",
                file=sys.stderr,
            )
            return 1

    duration_sample = [(run_id, durations_from_timings(timings)) for run_id, timings in sample]
    passed, failures = evaluate_policy(duration_sample, max_seconds=args.max_seconds)
    report = build_report(
        sample,
        max_seconds=args.max_seconds,
        passed=passed,
        failures=failures,
        sample_mode=sample_mode,
        created_after=args.created_after,
    )
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for run_id, timings in sample:
        print(_format_run_line(run_id, timings))
    if passed:
        label = (
            f"{len(sample)} explicit Gate run(s)"
            if sample_mode == "explicit_run_ids"
            else f"{len(sample)} successful Gate PR runs"
        )
        print(
            f"PASS: {label} have " f"{', '.join(TARGET_JOB_NAMES)} each <= {args.max_seconds:.0f}s"
        )
        return 0

    print("FAIL: Gate python job timing policy violated:", file=sys.stderr)
    for failure in failures:
        print(f"  - {failure}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
