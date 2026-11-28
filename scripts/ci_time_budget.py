#!/usr/bin/env python3
"""Daily advisory CI budget, with durable observations and a one-window drain.

Durations are minutes. Each Gate run contributes its slowest executed job;
short setup/summary jobs must not dilute the test matrix's bottleneck.
Workflows also reports advisory wall-clock timing through the Gate summary.

Filed issues ask an agent for the code change only; the multi-day series is
this job's observation, never an acceptance criterion. After a fix closes an
issue, refiling waits one series window so the trailing p50 holds only
post-fix runs.
Run with ``python -m scripts.ci_time_budget`` from the Workflows checkout.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from scripts import api_client
from scripts.list_registered_consumer_repos import extract_repos, is_owner_excluded

BASE_SHARE = 0.05
DOUBLING_DISTANCE = 0.25
MAX_SHARE = 0.5
TARGET_MINUTES = 10.0
WALL_CLOCK_THRESHOLD_MINUTES = 10.0
# ONE series window, defined once and consumed by every window this job applies:
# the trailing Gate measurement, the consecutive healthy daily p50s that close an
# issue, and the refile hold after a fix closes an issue. A shared name cannot
# drift; a matching pair of literals can (latched-gate rule).
SERIES_WINDOW_DAYS = 7
# This job posts RECOVERY_CLOSE_TEXT immediately before its recovery PATCH.
RECOVERY_CLOSE_TEXT = "Closing after confirmed recovery."
REPORT_PATH = Path("docs/reports/ci-budget.json")
REPORT_BRANCH = "ci-time-budget"
SOURCE_REPO = "stranske/Workflows"


class GitHub:
    """Use the shared retry client; never blindly retry issue creation."""

    def __init__(self, token: str):
        self.token = token
        self.cache_dir = Path(os.environ.get("CI_TIME_BUDGET_CACHE", ".cache/ci-time-budget"))

    def run_jobs(self, repo: str, run: dict) -> list[dict]:
        """Completed jobs are immutable for an exact run attempt/update revision."""
        if is_owner_excluded(repo):
            raise ValueError("Repository is excluded")
        path = f"/repos/{repo}/actions/runs/{run['id']}/jobs"
        identity = {key: run.get(key) for key in ("id", "run_attempt", "head_sha", "updated_at")}
        identity["repo"] = repo
        reusable = (
            run.get("status") == "completed"
            and type(identity["id"]) is int
            and identity["id"] > 0
            and type(identity["run_attempt"]) is int
            and identity["run_attempt"] > 0
            and re.fullmatch(r"[0-9a-f]{40}", str(identity["head_sha"]))
            and isinstance(identity["updated_at"], str)
            and identity["updated_at"]
        )
        if not reusable:
            return self.pages(path, "jobs", filter="latest")
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        cache = self.cache_dir / (key + ".json")
        try:
            with cache.open() as stream:
                raw = stream.read(16 * 1024 * 1024 + 1)
            saved = json.loads(raw)
            jobs = saved["jobs"]
            checksum = hashlib.sha256(json.dumps(jobs, sort_keys=True).encode()).hexdigest()
            if (
                len(raw) <= 16 * 1024 * 1024
                and saved.get("schema") == "ci-budget-jobs/v1"
                and saved.get("identity") == identity
                and saved.get("sha256") == checksum
                and isinstance(jobs, list)
                and jobs
                and all(
                    job.get("run_id") == run["id"] and job.get("status") == "completed"
                    for job in jobs
                )
            ):
                return jobs
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass  # a missing/partial cache is not a measurement
        jobs = self.pages(path, "jobs", filter="latest")
        if jobs and all(
            job.get("run_id") == run["id"] and job.get("status") == "completed" for job in jobs
        ):
            saved = {
                "schema": "ci-budget-jobs/v1",
                "identity": identity,
                "jobs": jobs,
                "sha256": hashlib.sha256(json.dumps(jobs, sort_keys=True).encode()).hexdigest(),
            }
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", dir=self.cache_dir, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(saved, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, cache)
        return jobs

    def request(self, method: str, path: str, payload: dict | None = None) -> Any:
        return api_client._request_json(
            method,
            f"{api_client.GITHUB_API}{path}",
            self.token,
            payload,
            max_attempts=3 if method == "GET" else 1,
        )

    def optional(self, path: str) -> Any:
        try:
            return self.request("GET", path)
        except RuntimeError as exc:
            if str(exc).startswith("GitHub API error 404:"):
                return None
            raise

    def pages(self, path: str, key: str | None = None, **params: Any) -> list[dict]:
        rows: list[dict] = []
        for page in range(1, 10001):
            data = self.request(
                "GET", f"{path}?{urlencode({**params, 'per_page': 100, 'page': page})}"
            )
            batch = data[key] if key else data
            rows.extend(batch)
            if len(batch) < 100:
                if key and len(rows) != data["total_count"]:
                    raise RuntimeError(f"Incomplete or changing pagination for {path}")
                return rows
        raise RuntimeError(f"Pagination limit reached for {path}")


def share(distance: float) -> float:
    """Match the issue's listed curve: 5% at .25, 10% at .5, 40% at 1."""
    if not math.isfinite(distance):
        raise ValueError("distance must be finite")
    if distance <= 0:
        return 0.0
    exponent = distance / DOUBLING_DISTANCE - 1
    # Bound the exponent before evaluating it, including extreme input values.
    return min(MAX_SHARE, BASE_SHARE * 2 ** min(exponent, math.log2(MAX_SHARE / BASE_SHARE)))


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def gate_runs(api: GitHub, repo: str, start: datetime, end: datetime) -> list[dict]:
    """Subdivide before Actions' 1,000-result filtered-query ceiling."""
    path = f"/repos/{repo}/actions/workflows/pr-00-gate.yml/runs"
    params = {"created": f"{start.isoformat()}..{end.isoformat()}", "status": "completed"}
    first = api.request("GET", f"{path}?{urlencode({**params, 'per_page': 1})}")
    if first["total_count"] > 1000:
        if (end - start).total_seconds() <= 1:
            raise RuntimeError("Gate run window exceeds the API ceiling within one second")
        mid = start + timedelta(seconds=int((end - start).total_seconds() / 2))
        halves = gate_runs(api, repo, start, mid) + gate_runs(api, repo, mid, end)
        unique = {run["id"]: run for run in halves}
        if len(unique) != first["total_count"]:
            raise RuntimeError("Gate run window changed during subdivision")
        return list(unique.values())
    # Read the recorded number of pages (an exactly-full last page needs no
    # extra query beyond the filtered API ceiling).
    runs: list[dict] = []
    for page in range(1, math.ceil(first["total_count"] / 100) + 1):
        data = api.request("GET", f"{path}?{urlencode({**params, 'per_page': 100, 'page': page})}")
        if data["total_count"] != first["total_count"]:
            raise RuntimeError("Gate run count changed while paging")
        runs.extend(data["workflow_runs"])
    if len({run["id"] for run in runs}) != first["total_count"]:
        raise RuntimeError("Incomplete Gate run window")
    return runs


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def measure(repo: str, *, api: GitHub, now: datetime) -> dict:
    if is_owner_excluded(repo):
        raise ValueError("Repository is excluded")
    start = now - timedelta(days=SERIES_WINDOW_DAYS)
    samples: list[float] = []
    longest: dict = {}
    wall_clock: list[float] = []
    matched_reruns = 0
    for run in gate_runs(api, repo, start, now):
        if run["conclusion"] not in {"success", "failure", "timed_out"}:
            continue
        durations: list[float] = []
        summaries: list[tuple[datetime, datetime]] = []
        read_jobs = getattr(api, "run_jobs", None)
        jobs = (
            read_jobs(repo, run)
            if callable(read_jobs)
            else api.pages(f"/repos/{repo}/actions/runs/{run['id']}/jobs", "jobs", filter="latest")
        )
        for job in jobs:
            if job["conclusion"] not in {"success", "failure", "timed_out"}:
                continue
            if not job.get("started_at") or not job.get("completed_at"):
                raise RuntimeError("Executed Gate job has no duration")
            started, completed = timestamp(job["started_at"]), timestamp(job["completed_at"])
            if not start <= started <= completed <= now:
                # Jobs outside the trailing window do not contribute samples.
                continue
            duration = (completed - started).total_seconds() / 60
            durations.append(duration)
            if repo == SOURCE_REPO and job["name"] == "summary":
                summaries.append((started, completed))
            if duration > longest.get("minutes", -1):
                longest = {"name": job["name"], "minutes": duration, "url": job["html_url"]}
        if durations:
            samples.append(max(durations))
            if len(summaries) == 1:
                try:
                    created = timestamp(run["created_at"])
                except (KeyError, ValueError, AttributeError):
                    continue  # Unavailable wall-clock input must not alter the budget.
                summary_started, summary_completed = summaries[0]
                if start <= created <= summary_started:
                    wall_clock.append((summary_completed - created).total_seconds() / 60)
                    attempt = run.get("run_attempt")
                    matched_reruns += int(type(attempt) is int and attempt > 1)
    if not samples:
        raise RuntimeError(
            f"No completed executed Gate jobs in the trailing {SERIES_WINDOW_DAYS} days"
        )
    result: dict = {
        "p50": percentile(samples, 0.5),
        "p90": percentile(samples, 0.9),
        "longest_job": longest,
        "sample_count": len(samples),
    }
    if repo == SOURCE_REPO:
        count = len(wall_clock)
        over = sum(value > WALL_CLOCK_THRESHOLD_MINUTES for value in wall_clock)
        result["gate_wall_clock"] = {
            "p50": percentile(wall_clock, 0.5) if count else None,
            "p90": percentile(wall_clock, 0.9) if count else None,
            "sample_count": count,
            "eligible_count": len(samples),
            "matched_rerun_count": matched_reruns,
            "over_10_minutes_count": over,
            "over_10_minutes_share": over / count if count else None,
        }
    return result


def observation(
    previous: dict, measured: dict | None, now: datetime, *, repo: str = SOURCE_REPO
) -> dict:
    today = now.date()
    history = dict(previous.get("p50_series", {}))
    history[today.isoformat()] = measured["p50"] if measured else None
    history = {
        day: value
        for day, value in sorted(history.items())
        if today - timedelta(days=SERIES_WINDOW_DAYS - 1) <= date.fromisoformat(day) <= today
    }
    healthy = 0
    for offset in range(SERIES_WINDOW_DAYS):
        p50 = history.get((today - timedelta(days=offset)).isoformat())
        if p50 is None or p50 > TARGET_MINUTES:
            break
        healthy += 1
    # Numeric history alone cannot identify the native observation that produced it.
    # Preserve actual dates only; a canceled/missed daily run contributes no date.
    observations = dict(previous.get("daily_observations", {}))
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if run_id.isdigit() and repo == os.environ.get("GITHUB_REPOSITORY") == SOURCE_REPO:
        observations[today.isoformat()] = {
            "date": today.isoformat(),
            "p50_minutes": measured["p50"] if measured else None,
            "run_id": int(run_id),
            "run_attempt": int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")),
            "measured_at": now.isoformat(),
            "window_start": (now - timedelta(days=SERIES_WINDOW_DAYS)).isoformat(),
            "source_run_url": f"https://github.com/{SOURCE_REPO}/actions/runs/{run_id}",
        }
    observations = {
        day: value
        for day, value in sorted(observations.items())
        if today - timedelta(days=29) <= date.fromisoformat(day) <= today
    }
    distance = max(0, measured["p50"] / TARGET_MINUTES - 1) if measured else None
    row = {
        **previous,
        "p50": None,
        "p90": None,
        "longest_job": None,
        "sample_count": 0,
        **(measured or {}),
        "target": TARGET_MINUTES,
        "distance": distance,
        "share": share(distance) if distance is not None else None,
        "drainable_in": SERIES_WINDOW_DAYS - healthy,
        "p50_series": history,
        "daily_observations": observations,
        "measured_at": now.isoformat(),
        "status": "measured" if measured else "unknown",
    }
    row.pop("error", None)
    if not measured or "gate_wall_clock" not in measured:
        row.pop("gate_wall_clock", None)  # Do not present an earlier window as current.
    if (
        distance is not None
        and distance > 0
        and (not previous.get("first_over_target_at") or previous.get("drained_at"))
    ):
        row["first_over_target_at"] = now.isoformat()
        for field in ("drained_at", "issue_filed_at", "filing_latency_hours", "filed_under_24h"):
            row.pop(field, None)
    return row


def issue_body(repo: str, row: dict, previous: dict | None = None) -> str:
    """Acceptance criteria are the code slice only: checkable on the fix PR itself.

    The multi-day series is Health 85's observation. It sits in its own section,
    stated as context, because an agent PR can never produce it and the closer
    judges every acceptance criterion at merge.
    """
    job = row["longest_job"]
    window = SERIES_WINDOW_DAYS
    earlier = ""
    if previous:
        earlier = (
            f"\nPrevious `ci-budget` issue: #{previous['number']}, closed "
            f"{previous['closed_at']}. One {window}-day series window has passed since "
            "then and the p50 is still over target.\n"
        )
    return f"""## Why

The trailing-{window}-day Gate p50 is {row['p50']:.2f} min against a
{row['target']:g} min target. Longest observed job: [{job['name']}]({job['url']})
({job['minutes']:.2f} min), in `.github/workflows/pr-00-gate.yml`.
Current share: {row['share']:.2%}; distance: {row['distance']:.3f};
drainable_in: {row['drainable_in']} days.
{earlier}
## Scope

Reduce the measured `{job['name']}` bottleneck in {repo}'s Gate without weakening checks.
The deliverable is the code change and its measured effect on this PR's own Gate run.

## Non-Goals

Do not waive required checks or block merges on duration. Do not wait for, or
report on, the multi-day Health 85 series: it is not part of this issue's
acceptance. Scaffold-only or partial completion does not count: a plan without a
code change to the named job is unfinished.

## Tasks

- [ ] Inspect the `{job['name']}` job in `.github/workflows/pr-00-gate.yml` and the workflow it calls, using the linked run; identify the duration bottleneck.
- [ ] Change the `{job['name']}` job, its called workflow, or the tests it runs to remove that bottleneck, keeping every required check.
- [ ] Record in the PR body the `{job['name']}` job duration from the PR head's Gate run (`gh run view <run-id> --json jobs`) next to the linked run's {job['minutes']:.2f} min, with both run URLs.

## Acceptance Criteria

- [ ] The PR diff changes the `{job['name']}` job, its called workflow, or the tests it runs, and the PR body names the bottleneck the change removes.
- [ ] `pr-00-gate.yml` passes on the PR head with the same required check names as the base branch, verified with `gh pr checks <pr-number>`.
- [ ] The PR body lists the `{job['name']}` duration from the PR head's own Gate run, read with `gh run view <run-id> --json jobs`, next to the linked over-target run's {job['minutes']:.2f} min, with both run URLs.

## Observation (Health 85 owns it; not an acceptance criterion)

Whether the change holds is measured by Health 85 over a {window}-day series, not by
this issue or its PR. Health 85 closes this issue itself after {window} consecutive
daily p50s at or below {row['target']:g} min. If this issue is closed when the fix
merges, Health 85 does not refile for one {window}-day series window after that
close, so its trailing window holds only post-fix runs; after that it refiles only
if the p50 is still over target, citing this issue.

## Implementation Notes

Health 85 updates measurements daily. The opener reserves `ceil(share * cap)`
slots for this repo before other materializations; the coordinator applies that
rule. Source report: `{SOURCE_REPO}@{REPORT_BRANCH}:{REPORT_PATH}`.
First over-target measurement: {row.get('first_over_target_at', 'unknown')}.
<!-- ci-time-budget:v1 -->
"""


def is_recovery_close(api: GitHub, root: str, issue: dict) -> bool:
    """Was the issue's latest close this job's recovery close? Read from its timeline.

    The evidence is on GitHub, not in the report, so it survives a failed publish
    after reconciliation. It is tied to the close event by order, not by a time
    window: walking back from the latest `closed` event, the recovery comment must
    come before any `reopened` or earlier `closed` event. A reopened issue that a
    fix then closes, however soon, has a `reopened` event in between.
    """
    timeline = api.pages(f"{root}/issues/{issue['number']}/timeline")
    closes = [i for i, item in enumerate(timeline) if item.get("event") == "closed"]
    if not closes:
        return False
    for item in reversed(timeline[: closes[-1]]):
        if item.get("event") in {"reopened", "closed"}:
            return False
        if item.get("event") == "commented" and RECOVERY_CLOSE_TEXT in (item.get("body") or ""):
            return True
    return False


def last_fixed_issue(api: GitHub, root: str) -> dict | None:
    """Newest `ci-budget` issue closed as completed, unless that close was this job's recovery.

    The closer closes an issue when its fix PR merges, so `closed_at` is at or
    after the merge: a hold anchored on it ends at or after merge + one window.
    When the newest close is this job's recovery close, a full healthy window has
    already been observed since any earlier fix, so nothing holds.
    `not_planned`/`duplicate` closes had no fix.
    """
    closed = [
        issue
        for issue in api.pages(f"{root}/issues", state="closed", labels="ci-budget")
        if "pull_request" not in issue
        and issue.get("closed_at")
        and issue.get("state_reason") not in {"not_planned", "duplicate"}
    ]
    newest = max(closed, key=lambda issue: timestamp(issue["closed_at"]), default=None)
    if newest is None or is_recovery_close(api, root, newest):
        return None
    return newest


def refile_hold(previous: dict | None, now: datetime) -> dict | None:
    """Blocking quantity and clear time together; None when nothing holds."""
    if previous is None:
        return None
    clears = timestamp(previous["closed_at"]) + timedelta(days=SERIES_WINDOW_DAYS)
    remaining = (clears - now).total_seconds() / 86400
    if remaining <= 0:
        return None
    return {
        "previous_issue": previous["number"],
        "fix_closed_at": previous["closed_at"],
        "window_days": SERIES_WINDOW_DAYS,
        "remaining_days": round(remaining, 2),
        "clears_at": clears.isoformat(),
    }


def reconcile(api: GitHub, repo: str, row: dict) -> None:
    """Idempotent filing and recovery; an unknown measurement authorizes no mutation."""
    row.pop("refile_hold", None)  # recomputed below; never shown from an earlier day
    if row["share"] is None:
        return
    root = f"/repos/{repo}"
    issues = [
        issue
        for issue in api.pages(f"{root}/issues", state="open", labels="ci-budget")
        if "pull_request" not in issue
    ]
    if row["share"] > 0:
        previous = None
        if not issues:
            previous = last_fixed_issue(api, root)
            hold = refile_hold(previous, timestamp(row["measured_at"]))
            if hold:
                # The fix's series window has not elapsed: the trailing p50 still
                # contains pre-fix runs. The same daily run that measures clears it.
                row["refile_hold"] = hold
                row["issue_numbers"] = []
                print(
                    f"{repo}: refile held: ci-budget #{hold['previous_issue']} closed "
                    f"{hold['fix_closed_at']} (fix merged); series window "
                    f"{hold['window_days']} d; hold {hold['remaining_days']:.2f} d; "
                    f"clears_at={hold['clears_at']}; share={row['share']:.2%}"
                )
                return
        if not issues:
            for label, color in (("ci-budget", "1d76db"), ("priority:high", "b60205")):
                if api.optional(f"{root}/labels/{quote(label, safe='')}") is None:
                    api.request("POST", f"{root}/labels", {"name": label, "color": color})
            issues = [
                api.request(
                    "POST",
                    f"{root}/issues",
                    {
                        "title": f"perf(ci): reduce Gate p50 toward {row['target']:g} min",
                        "body": issue_body(repo, row, previous),
                        "labels": ["ci-budget", "priority:high"],
                    },
                )
            ]
            if previous:
                print(
                    f"{repo}: hold 0 d (series window after #{previous['number']} ended); "
                    f"refiled #{issues[0]['number']}"
                )
        filed = min(issue["created_at"] for issue in issues)
        row["issue_filed_at"] = filed
        first = row.get("first_over_target_at")
        row["filing_latency_hours"] = (
            max(0, (timestamp(filed) - timestamp(first)).total_seconds() / 3600) if first else None
        )
        latency = row["filing_latency_hours"]
        row["filed_under_24h"] = latency < 24 if latency is not None else None
    row["issue_numbers"] = [issue["number"] for issue in issues]
    day = row["measured_at"][:10]
    if issues and row["drainable_in"] == 0:
        series = ", ".join(f"{day}: {p50:.2f} min" for day, p50 in row["p50_series"].items())
        for issue in issues:
            api.request(
                "POST",
                f"{root}/issues/{issue['number']}/comments",
                {
                    "body": f"{SERIES_WINDOW_DAYS} consecutive under-target daily p50s: "
                    f"{series}.\n"
                    f"share=0, drainable_in=0. {RECOVERY_CLOSE_TEXT}"
                },
            )
            api.request("PATCH", f"{root}/issues/{issue['number']}", {"state": "closed"})
        row["issue_numbers"] = []
        row["drained_at"] = row["measured_at"]
        print(f"{repo}: share=0, issue closed; p50_series={series}")
    elif issues and row.get("issue_updated_on") != day:
        for issue in issues:
            api.request(
                "POST",
                f"{root}/issues/{issue['number']}/comments",
                {
                    "body": f"CI budget {day}: p50={row['p50']:.2f} min; "
                    f"target={row['target']:g} min; distance={row['distance']:.3f}; "
                    f"share={row['share']:.2%}; drainable_in={row['drainable_in']}; "
                    f"longest_job={row['longest_job']['name']}."
                },
            )
        row["issue_updated_on"] = day


def load_report(api: GitHub) -> tuple[dict, str | None]:
    ref = api.optional(f"/repos/{SOURCE_REPO}/git/ref/heads/{REPORT_BRANCH}")
    if ref is None:
        return {}, None
    data = api.request("GET", f"/repos/{SOURCE_REPO}/contents/{REPORT_PATH}?ref={REPORT_BRANCH}")
    return json.loads(base64.b64decode(data["content"])), data["sha"]


def publish(report: dict, *, api: GitHub, sha: str | None) -> str:
    """Persist both the published report and recovery state via contents CAS."""
    content = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(content, encoding="utf-8")
    if sha is None:
        # Build the initial report commit before creating the ref. A lost file
        # write must not leave an empty state branch that cannot be resumed.
        repo = api.request("GET", f"/repos/{SOURCE_REPO}")
        ref = api.request("GET", f"/repos/{SOURCE_REPO}/git/ref/heads/{repo['default_branch']}")
        parent = ref["object"]["sha"]
        commit = api.request("GET", f"/repos/{SOURCE_REPO}/git/commits/{parent}")
        blob = api.request(
            "POST", f"/repos/{SOURCE_REPO}/git/blobs", {"content": content, "encoding": "utf-8"}
        )
        tree = api.request(
            "POST",
            f"/repos/{SOURCE_REPO}/git/trees",
            {
                "base_tree": commit["tree"]["sha"],
                "tree": [
                    {"path": str(REPORT_PATH), "mode": "100644", "type": "blob", "sha": blob["sha"]}
                ],
            },
        )
        report_commit = api.request(
            "POST",
            f"/repos/{SOURCE_REPO}/git/commits",
            {
                "message": "chore(ci): initialize CI time budget [skip ci]",
                "tree": tree["sha"],
                "parents": [parent],
            },
        )
        api.request(
            "POST",
            f"/repos/{SOURCE_REPO}/git/refs",
            {"ref": f"refs/heads/{REPORT_BRANCH}", "sha": report_commit["sha"]},
        )
        return blob["sha"]
    payload = {
        "message": "chore(ci): publish daily CI time budget [skip ci]",
        "content": base64.b64encode(content.encode()).decode(),
        "branch": REPORT_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    result = api.request("PUT", f"/repos/{SOURCE_REPO}/contents/{REPORT_PATH}", payload)
    return result["content"]["sha"]


def run(api: GitHub, repos: list[str], now: datetime) -> int:
    previous, sha = load_report(api)
    report: dict = {}
    errors: list[str] = []
    for repo in sorted(set(repos) | {SOURCE_REPO}):
        if is_owner_excluded(repo):
            continue
        try:
            measured = measure(repo, api=api, now=now)
            report[repo] = observation(previous.get(repo, {}), measured, now, repo=repo)
        except (RuntimeError, ValueError, KeyError) as exc:
            report[repo] = observation(previous.get(repo, {}), None, now, repo=repo)
            report[repo]["error"] = str(exc)
            errors.append(f"{repo}: measurement unavailable")
    # Persist first detection before filing. A crash or denied issue write cannot
    # erase the start of the <24h filing-latency clock on the next daily run.
    sha = publish(report, api=api, sha=sha)
    for repo, row in report.items():
        try:
            reconcile(api, repo, row)
        except (RuntimeError, ValueError, KeyError) as exc:
            row["error"] = str(exc)
            errors.append(f"{repo}: issue reconciliation failed")
        print(
            f"{repo}: p50={row['p50']} p90={row['p90']} target={row['target']} "
            f"distance={row['distance']} share={row['share']} drainable_in={row['drainable_in']} "
            f"filing_latency_hours={row.get('filing_latency_hours')} "
            f"filed_under_24h={row.get('filed_under_24h')} issues={row.get('issue_numbers', [])} "
            f"refile_hold_clears_at={(row.get('refile_hold') or {}).get('clears_at')}"
        )
        if timing := row.get("gate_wall_clock"):
            print(
                f"{repo}: Gate wall clock (minutes, advisory): "
                f"p50={timing['p50']} p90={timing['p90']} "
                f"coverage={timing['sample_count']}/{timing['eligible_count']} "
                f"over_10m={timing['over_10_minutes_count']} "
                f"over_10m_share={timing['over_10_minutes_share']}"
            )
    publish(report, api=api, sha=sha)
    for error in errors:
        print(f"ERROR: {error}")
    return int(bool(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise SystemExit(
            "GH_TOKEN with fleet Actions/Issues and source Contents access is required"
        )
    repos = extract_repos(Path(".github/workflows/maint-68-sync-consumer-repos.yml"))
    return run(GitHub(token), repos, datetime.now(UTC).replace(microsecond=0))


if __name__ == "__main__":
    raise SystemExit(main())
