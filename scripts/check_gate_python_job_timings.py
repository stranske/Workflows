#!/usr/bin/env python3
"""Assert Hosted Gate python jobs stay within the single-runtime timing policy.

Issue #4260 acceptance: across the N latest successful Workflows Gate pull_request
runs, ``python ci / python 3.13`` and ``python ci / python 3.14`` must each finish
in at most ``max-seconds`` (default 600 = 10 minutes).

Pure evaluation helpers are unit-tested; live GitHub reads go through the shared
api_client wrapper (via workflow_startup_failure_diagnostic._gh_api).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
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

JsonGetter = Callable[[str, str], dict[str, Any]]


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


def extract_python_job_durations(jobs: list[Any]) -> dict[str, float]:
    """Map target python job names to durations found in a jobs payload."""
    durations: dict[str, float] = {}
    for job in jobs:
        if not isinstance(job, dict):
            continue
        name = str(job.get("name") or "")
        if name not in TARGET_JOB_NAMES:
            continue
        duration = job_duration_seconds(job)
        if duration is not None:
            durations[name] = duration
    return durations


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
    selected: list[dict[str, Any]] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        if str(run.get("conclusion") or "") != "success":
            continue
        selected.append(run)
        if len(selected) >= limit:
            break
    return selected


def collect_run_python_durations(
    *,
    repo: str,
    run_id: int | str,
    token: str,
    get_json: JsonGetter | None = None,
) -> dict[str, float]:
    """Fetch jobs for one run and return target python job durations."""
    fetch = get_json or _gh_api
    payload = fetch(f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100", token)
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError(f"Unexpected jobs payload for run {run_id}")
    return extract_python_job_durations(jobs)


def collect_policy_sample(
    *,
    repo: str = DEFAULT_REPO,
    workflow: str = DEFAULT_WORKFLOW,
    limit: int = DEFAULT_RUN_LIMIT,
    token: str | None = None,
    get_json: JsonGetter | None = None,
) -> list[tuple[int | str, dict[str, float]]]:
    """Build (run_id, durations) pairs for the policy sample window."""
    auth = token or _github_token()
    fetch = get_json or _gh_api
    runs = list_successful_pr_runs(
        repo=repo, workflow=workflow, limit=limit, token=auth, get_json=fetch
    )
    sample: list[tuple[int | str, dict[str, float]]] = []
    for run in runs:
        run_id = run.get("id")
        if run_id is None:
            continue
        durations = collect_run_python_durations(
            repo=repo, run_id=run_id, token=auth, get_json=fetch
        )
        sample.append((run_id, durations))
    return sample


def build_report(
    sample: list[tuple[int | str, dict[str, float]]],
    *,
    max_seconds: float,
    passed: bool,
    failures: list[str],
    sample_mode: str = "successful_pr_window",
) -> dict[str, Any]:
    """Machine-readable report for evidence / Nov 15 acceptance reads."""
    return {
        "policy": {
            "max_seconds": max_seconds,
            "required_jobs": list(TARGET_JOB_NAMES),
            "run_count": len(sample),
            "sample_mode": sample_mode,
        },
        "passed": passed,
        "failures": failures,
        "runs": [
            {
                "run_id": run_id,
                "jobs": {
                    name: {"seconds": seconds, "within_policy": seconds <= max_seconds}
                    for name, seconds in sorted(durations.items())
                },
            }
            for run_id, durations in sample
        ],
    }


def collect_run_ids_sample(
    *,
    repo: str,
    run_ids: list[int | str],
    token: str | None = None,
    get_json: JsonGetter | None = None,
) -> list[tuple[int | str, dict[str, float]]]:
    """Build (run_id, durations) pairs for explicit Gate run ids (any conclusion)."""
    if not run_ids:
        raise ValueError("run_ids must be non-empty")
    auth = token or _github_token()
    fetch = get_json or _gh_api
    sample: list[tuple[int | str, dict[str, float]]] = []
    for run_id in run_ids:
        durations = collect_run_python_durations(
            repo=repo, run_id=run_id, token=auth, get_json=fetch
        )
        sample.append((run_id, durations))
    return sample


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

    if args.run_ids:
        sample = collect_run_ids_sample(repo=args.repo, run_ids=list(args.run_ids))
        sample_mode = "explicit_run_ids"
    else:
        sample = collect_policy_sample(repo=args.repo, workflow=args.workflow, limit=args.limit)
        sample_mode = "successful_pr_window"
        if len(sample) < args.limit:
            print(
                f"Only found {len(sample)} successful {DEFAULT_EVENT} runs "
                f"(needed {args.limit})",
                file=sys.stderr,
            )
            return 1

    passed, failures = evaluate_policy(sample, max_seconds=args.max_seconds)
    report = build_report(
        sample,
        max_seconds=args.max_seconds,
        passed=passed,
        failures=failures,
        sample_mode=sample_mode,
    )
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for run_id, durations in sample:
        parts = [f"{name}={seconds:.0f}s" for name, seconds in sorted(durations.items())]
        print(f"run {run_id}: " + (", ".join(parts) if parts else "no target jobs"))
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
