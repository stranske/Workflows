#!/usr/bin/env python3
"""Daily advisory CI budget, with durable observations and a seven-day drain.

Durations are minutes. Each Gate run contributes its slowest executed job;
short setup/summary jobs must not dilute the test matrix's bottleneck.
Run with ``python -m scripts.ci_time_budget`` from the Workflows checkout.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
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
RECOVERY_DAYS = 7
REPORT_PATH = Path("docs/reports/ci-budget.json")
REPORT_BRANCH = "ci-time-budget"
SOURCE_REPO = "stranske/Workflows"


class GitHub:
    """Use the shared retry client; never blindly retry issue creation."""

    def __init__(self, token: str):
        self.token = token

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
    start = now - timedelta(days=7)
    samples: list[float] = []
    longest: dict = {}
    for run in gate_runs(api, repo, start, now):
        if run["conclusion"] not in {"success", "failure", "timed_out"}:
            continue
        durations: list[float] = []
        for job in api.pages(
            f"/repos/{repo}/actions/runs/{run['id']}/jobs", "jobs", filter="latest"
        ):
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
            if duration > longest.get("minutes", -1):
                longest = {"name": job["name"], "minutes": duration, "url": job["html_url"]}
        if durations:
            samples.append(max(durations))
    if not samples:
        raise RuntimeError("No completed executed Gate jobs in the trailing seven days")
    return {
        "p50": percentile(samples, 0.5),
        "p90": percentile(samples, 0.9),
        "longest_job": longest,
        "sample_count": len(samples),
    }


def observation(previous: dict, measured: dict | None, now: datetime) -> dict:
    today = now.date()
    history = dict(previous.get("p50_series", {}))
    history[today.isoformat()] = measured["p50"] if measured else None
    history = {
        day: value
        for day, value in sorted(history.items())
        if today - timedelta(days=RECOVERY_DAYS - 1) <= date.fromisoformat(day) <= today
    }
    healthy = 0
    for offset in range(RECOVERY_DAYS):
        p50 = history.get((today - timedelta(days=offset)).isoformat())
        if p50 is None or p50 > TARGET_MINUTES:
            break
        healthy += 1
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
        "drainable_in": RECOVERY_DAYS - healthy,
        "p50_series": history,
        "measured_at": now.isoformat(),
        "status": "measured" if measured else "unknown",
    }
    row.pop("error", None)
    if (
        distance is not None
        and distance > 0
        and (not previous.get("first_over_target_at") or previous.get("drained_at"))
    ):
        row["first_over_target_at"] = now.isoformat()
        for field in ("drained_at", "issue_filed_at", "filing_latency_hours", "filed_under_24h"):
            row.pop(field, None)
    return row


def issue_body(repo: str, row: dict) -> str:
    job = row["longest_job"]
    return f"""## Why

The trailing-seven-day Gate p50 is {row['p50']:.2f} min against a
{row['target']:g} min target. Longest observed job: [{job['name']}]({job['url']})
({job['minutes']:.2f} min), in `.github/workflows/pr-00-gate.yml`.
Current share: {row['share']:.2%}; distance: {row['distance']:.3f};
drainable_in: {row['drainable_in']} days.

## Scope

Reduce the measured `{job['name']}` bottleneck in {repo}'s Gate without weakening checks.

## Non-Goals

Do not waive required checks or block merges on duration. Scaffold-only or partial
completion does not count: a plan without a measured reduction is unfinished.

## Tasks

- [ ] Inspect `{job['name']}` in `.github/workflows/pr-00-gate.yml` and its called workflow using the linked run; identify the duration bottleneck.
- [ ] Implement a bounded change to that job or its invoked tests, preserving required validation.
- [ ] Compare Gate durations before/after and attach run URLs and measurements.

## Acceptance Criteria

- [ ] `pr-00-gate.yml` passes with required checks preserved after the change.
- [ ] Health 85 reports trailing-seven-day Gate p50 at or below {row['target']:g} min for seven consecutive daily measurements, then closes this issue with the dated p50 series.

## Implementation Notes

Health 85 updates measurements daily. The opener reserves `ceil(share * cap)`
slots for this repo before other materializations; the coordinator applies that
rule. Source report: `{SOURCE_REPO}@{REPORT_BRANCH}:{REPORT_PATH}`.
First over-target measurement: {row.get('first_over_target_at', 'unknown')}.
<!-- ci-time-budget:v1 -->
"""


def reconcile(api: GitHub, repo: str, row: dict) -> None:
    """Idempotent filing and recovery; an unknown measurement authorizes no mutation."""
    if row["share"] is None:
        return
    root = f"/repos/{repo}"
    issues = [
        issue
        for issue in api.pages(f"{root}/issues", state="open", labels="ci-budget")
        if "pull_request" not in issue
    ]
    if row["share"] > 0:
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
                        "body": issue_body(repo, row),
                        "labels": ["ci-budget", "priority:high"],
                    },
                )
            ]
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
                    "body": f"Seven consecutive under-target daily p50s: {series}.\n"
                    "share=0, drainable_in=0. Closing after confirmed recovery."
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
            report[repo] = observation(previous.get(repo, {}), measured, now)
        except (RuntimeError, ValueError, KeyError) as exc:
            report[repo] = observation(previous.get(repo, {}), None, now)
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
            f"filed_under_24h={row.get('filed_under_24h')} issues={row.get('issue_numbers', [])}"
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
