#!/usr/bin/env python3
"""Assert durable tracker source workflows executed inside their cadence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# scripts/check_api_wrapper_guard.py forbids raw GitHub API shell-outs in
# scripts/: everything goes through the sanctioned api_client wrapper. (That guard
# matches comment text too, so this note deliberately avoids naming the banned
# invocation literally.) Reusing the sweep's fetch also means ONE probe
# implementation and ONE rate-limit policy for the two liveness tools, which is
# the consolidation #3189 raised. It brings pacing plus a real backoff for
# GitHub's SECONDARY rate limit - a separate cap on rapid sequential requests,
# invisible to /rate_limit - which this probe previously had no defence against
# at all: one 403 aborted the whole liveness check.
from scripts.workflow_startup_failure_diagnostic import _gh_api  # noqa: E402

CONFIG_PATH = REPO_ROOT / "config" / "durable_tracker_liveness.yml"
TRACKER_DOC = REPO_ROOT / "docs" / "ops" / "DURABLE_TRACKING_ISSUES.md"
EXECUTABLE_CONCLUSIONS = frozenset({"success", "failure", "cancelled", "timed_out"})

# How many job-level-executable runs to probe across a complete lookup when a tracker
# configures `require_step`. Bounded so a workflow that has been debouncing for weeks
# costs a fixed number of jobs calls rather than one per run in its history.
STEP_PROBE_LIMIT = 20


def _github_token() -> str:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    return subprocess.check_output(["gh", "auth", "token"], text=True).strip()


def _load_config() -> list[dict[str, Any]]:
    """Every monitored workflow: durable trackers first, then execution-only entries.

    `execution_liveness` entries are monitored the same way but own NO durable
    tracker issue, so they are excluded from the config-vs-doc coverage equality in
    `main()` and are never commented on. Health 68 is the motivating case: its #2210
    is a TRANSIENT alert that the workflow itself opens and closes (see
    docs/ops/DURABLE_TRACKING_ISSUES.md, "Distinguishing trackers from transient
    alerts"), so listing it under `trackers:` would assert a durable relationship
    that does not exist — the same false machine-readable claim #3244 is about.
    """
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    trackers = data.get("trackers")
    if not isinstance(trackers, list) or not trackers:
        raise ValueError(f"{CONFIG_PATH} must define a non-empty trackers list")
    entries = [{**entry, "durable": True} for entry in trackers]
    execution_only = data.get("execution_liveness") or []
    if not isinstance(execution_only, list):
        raise ValueError(f"{CONFIG_PATH} execution_liveness must be a list when present")
    entries.extend({**entry, "durable": False} for entry in execution_only)
    return entries


def _durable_tracker_workflows() -> set[tuple[str, str]]:
    """Return durable coverage keys without collapsing identical consumer workflows."""
    return {
        (str(entry.get("repo") or "stranske/Workflows"), str(entry["workflow"]))
        for entry in _load_config()
        if entry.get("durable")
    }


def tracker_doc_workflows() -> set[tuple[str, str]]:
    import re

    text = TRACKER_DOC.read_text(encoding="utf-8")
    section_match = re.search(
        r"## Current durable trackers\n\n\| Issue.*?\n\|[-| ]+\n(.*?)(?:\n\n|\n### )",
        text,
        re.DOTALL,
    )
    assert section_match, "DURABLE_TRACKING_ISSUES.md is missing the tracker table"
    table_body = section_match.group(1)
    rows = re.findall(
        r"\| \[#\d+\]\(https://github\.com/([^/]+/[^/]+)/issues/\d+\) \|.*?\| \[`([^`]+)`\]",
        table_body,
    )
    return {(repo, workflow) for repo, workflow in rows if workflow.endswith(".yml")}


def run_step_conclusion(
    repo: str,
    run_id: Any,
    step_name: str,
    token: str,
) -> str | None:
    """Conclusion of ``step_name`` in ``run_id``, or None when the step is absent.

    None means "this run has no such step" — a different fact from "the step ran
    and was skipped", which returns ``"skipped"``. Collapsing the two is the
    defect this module is being fixed for, one level up.
    """
    payload = _gh_api(f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100", token)
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        return None
    for job in jobs:
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if isinstance(step, dict) and str(step.get("name") or "") == step_name:
                return str(step.get("conclusion") or "")
    return None


def _latest_executable_run(
    repo: str,
    workflow_file: str,
    token: str,
    allowed_events: frozenset[str] | None = None,
    require_step: str | None = None,
    branch: str | None = None,
) -> dict[str, Any] | None:
    """Newest run of ``workflow_file`` that actually executed, or None.

    Returns None only when the history genuinely contains no executable run. A
    failed lookup RAISES (via the wrapper) rather than returning None, because
    None reads as "no executable run" and would blame the workflow for the
    checker's own inability to look.

    ``require_step`` narrows "executed" from the JOB conclusion to a named STEP.
    A job whose work step was skipped still concludes ``success`` — Health 68's
    debounce does exactly that — so without this the newest run is evidence that
    the workflow was TRIGGERED, never that it did anything. With it, a run counts
    only when the named step reached a conclusion other than ``skipped``.
    When ``require_step`` is None the job conclusion is used, unchanged.
    """
    base_path = f"repos/{repo}/actions/workflows/{workflow_file}/runs?per_page=100"
    if branch is not None:
        base_path += f"&branch={branch}"
    events: tuple[str | None, ...] = tuple(sorted(allowed_events)) if allowed_events else (None,)

    def runs_path(event: str | None, page: int) -> str:
        path = base_path
        if event is not None:
            return f"{path}&event={event}&page={page}"
        return f"{path}&page={page}" if page > 1 else path

    def executable_runs(path: str) -> tuple[list[dict[str, Any]], bool]:
        payload = _gh_api(path, token)
        runs = payload.get("workflow_runs")
        if not isinstance(runs, list):
            return [], True
        return (
            [
                run
                for run in runs
                if isinstance(run, dict)
                and str(run.get("conclusion") or "") in EXECUTABLE_CONCLUSIONS
            ],
            len(runs) < 100,
        )

    candidates: list[dict[str, Any]] = []
    if require_step is None:
        for event in events:
            page = 1
            while True:
                executable, exhausted = executable_runs(runs_path(event, page))
                if executable:
                    candidates.append(executable[0])
                    break
                if exhausted:
                    break
                page += 1
    else:
        # Probe one run from each configured event stream before returning to the
        # next run in any stream.  The cap remains global, but an older event (for
        # example, schedule) cannot spend every probe before a newer permitted
        # event (for example, workflow_dispatch) gets a chance to qualify.
        states = [
            {
                "event": event,
                "page": 1,
                "pending": [],
                "exhausted": False,
                "complete": False,
            }
            for event in events
        ]
        remaining_step_probes = STEP_PROBE_LIMIT
        while remaining_step_probes > 0:
            progressed = False
            for state in states:
                if remaining_step_probes <= 0:
                    break
                if state["complete"]:
                    continue
                while not state["pending"] and not state["exhausted"]:
                    executable, exhausted = executable_runs(
                        runs_path(state["event"], state["page"])
                    )
                    state["page"] += 1
                    state["pending"].extend(executable)
                    state["exhausted"] = exhausted
                if not state["pending"]:
                    continue
                progressed = True
                run = state["pending"].pop(0)
                remaining_step_probes -= 1
                conclusion = run_step_conclusion(repo, run.get("id"), require_step, token)
                if conclusion is not None and conclusion != "skipped":
                    candidate = dict(run)
                    candidate["required_step_conclusion"] = conclusion
                    candidates.append(candidate)
                    state["complete"] = True
            if not progressed:
                break
    if not candidates:
        return None
    return max(candidates, key=lambda run: str(run.get("created_at") or ""))


def _held_by_workflow_protection(runs_probe_empty: bool, repo: str, workflow_file: str) -> str:
    """Name the hold explicitly when that is why nothing executed.

    "no executable run found" is true but unactionable. If every recent run is a
    zero-job ``action_required``, the cause is GitHub's suspicious-workflow
    protection, no REST endpoint clears it, and the remedy is a web-UI approval.
    Saying so turns a tracker comment into something someone can act on.
    """
    if not runs_probe_empty:
        return ""
    return (
        f" Every recent run of {workflow_file} concluded action_required with zero jobs, "
        f"which is GitHub's suspicious-workflow protection, not a scheduling problem. "
        f"No REST endpoint clears it: use Approve and run in the web UI. "
        f"See scripts/workflow_startup_failure_diagnostic.py --sweep --repo {repo} "
        f"for the fleet-wide view and a benign/needs-eyes verdict per held workflow."
    )


def _recent_workflow_runs(
    repo: str,
    workflow_file: str,
    token: str,
    allowed_events: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    """Return recent runs constrained to the same event scope as liveness."""
    events: tuple[str | None, ...] = tuple(sorted(allowed_events)) if allowed_events else (None,)
    runs: list[dict[str, Any]] = []
    for event in events:
        path = f"repos/{repo}/actions/workflows/{workflow_file}/runs?per_page=100"
        if event is not None:
            path += f"&event={event}"
        payload = _gh_api(path, token)
        candidates = payload.get("workflow_runs")
        if isinstance(candidates, list):
            runs.extend(run for run in candidates if isinstance(run, dict))
    return runs


def _held_zero_job_run_count(
    repo: str,
    workflow_file: str,
    token: str,
    allowed_events: frozenset[str] | None = None,
) -> int:
    """Count recent zero-job protection holds for a tracker alert."""
    held = [
        run
        for run in _recent_workflow_runs(repo, workflow_file, token, allowed_events)
        if run.get("conclusion") == "action_required"
    ]
    return sum(
        _gh_api(f"repos/{repo}/actions/runs/{run.get('id')}/jobs?per_page=1", token).get(
            "total_count"
        )
        == 0
        for run in held
    )


def _no_executable_run_reason(
    repo: str,
    workflow_file: str,
    token: str,
    allowed_events: frozenset[str] | None = None,
) -> str:
    """Explain an absent executable run without mistaking every absence for a hold."""
    runs = _recent_workflow_runs(repo, workflow_file, token, allowed_events)
    if not runs:
        return "no workflow runs found."
    conclusions = {str(run.get("conclusion") or "") for run in runs if isinstance(run, dict)}
    held = [run for run in runs if run.get("conclusion") == "action_required"]
    if held:
        held_zero_job = []
        for run in held:
            jobs = _gh_api(f"repos/{repo}/actions/runs/{run.get('id')}/jobs?per_page=1", token)
            if jobs.get("total_count") == 0:
                held_zero_job.append(run)
        if held_zero_job and len(held_zero_job) == len(runs):
            return (
                "no executable run found (only action_required zero-job runs)."
                + _held_by_workflow_protection(True, repo, workflow_file)
            )
    if conclusions == {"skipped"}:
        return "no executable run found (only skipped runs)."
    return f"no executable run found (recent conclusions: {', '.join(sorted(conclusions)) or 'unknown'})."


def _hours_since(iso_timestamp: str) -> float:
    created = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    return (datetime.now(UTC) - created).total_seconds() / 3600.0


def evaluate_trackers(repo: str, token: str | None = None) -> list[dict[str, Any]]:
    auth = token or _github_token()
    results: list[dict[str, Any]] = []
    for entry in _load_config():
        workflow = str(entry["workflow"])
        target_repo = str(entry.get("repo") or repo)
        raw_issue = entry.get("issue")
        issue = int(raw_issue) if raw_issue is not None else None
        if entry.get("event_driven") is True:
            results.append(
                {
                    "repo": target_repo,
                    "workflow": workflow,
                    "issue": issue,
                    "healthy": True,
                    "reason": "event-driven workflow excluded from age-based liveness",
                }
            )
            continue
        max_age_hours = float(entry["max_age_hours"])
        configured_events = entry.get("events")
        allowed_events = (
            frozenset(str(event) for event in configured_events)
            if isinstance(configured_events, list) and configured_events
            else None
        )
        require_step = entry.get("require_step")
        require_step = str(require_step) if require_step else None
        latest = _latest_executable_run(target_repo, workflow, auth, allowed_events)
        if latest is None:
            result = {
                "repo": target_repo,
                "workflow": workflow,
                "issue": issue,
                "healthy": False,
                "reason": _no_executable_run_reason(target_repo, workflow, auth, allowed_events),
            }
            result["held_zero_job_run_count"] = _held_zero_job_run_count(
                target_repo, workflow, auth, allowed_events
            )
            results.append(result)
            continue
        hours = _hours_since(str(latest["created_at"]))
        result: dict[str, Any] = {
            "repo": target_repo,
            "workflow": workflow,
            "issue": issue,
            "healthy": hours <= max_age_hours,
            "latest_conclusion": latest.get("conclusion"),
            "latest_created_at": latest.get("created_at"),
            "latest_event": latest.get("event"),
            "hours_since": round(hours, 2),
            "max_age_hours": max_age_hours,
            "run_url": latest.get("html_url"),
        }
        if not result["healthy"]:
            result["held_zero_job_run_count"] = _held_zero_job_run_count(
                target_repo, workflow, auth, allowed_events
            )

        # THE BLOCKING QUANTITY AND THE DRAINABLE QUANTITY, SIDE BY SIDE.
        # `hours_since` alone answers "was this workflow triggered recently", which a
        # debounced no-op satisfies forever. `hours_since_executing_run` answers "did
        # it DO anything recently", which is the number the tracker actually depends
        # on. Reporting only the first is what let seven consecutive comparison-free
        # `success` runs read as health.
        if require_step is not None:
            result["require_step"] = require_step
            executed = _latest_executable_run(
                target_repo,
                workflow,
                auth,
                allowed_events,
                require_step,
                branch="main",
            )
            if executed is None:
                # Distinguishable from "no runs at all" above: runs exist, they
                # concluded, and not one of them ran the step. Never silently reuse
                # `hours_since` here — that would rebuild the very defect this branch
                # exists to detect, one level up.
                result["latest_executing_created_at"] = None
                result["hours_since_executing_run"] = None
                result["healthy"] = False
                result["reason"] = (
                    f"no run in the {STEP_PROBE_LIMIT} newest executable runs ran step "
                    f"{require_step!r}; every one of them concluded without doing the work, "
                    f"so the newest run at {latest.get('created_at')} is evidence the workflow "
                    f"was triggered, not that it executed."
                )
            else:
                executing_hours = _hours_since(str(executed["created_at"]))
                result["latest_executing_created_at"] = executed.get("created_at")
                result["latest_executing_conclusion"] = executed.get("conclusion")
                result["required_step_conclusion"] = executed.get("required_step_conclusion")
                result["hours_since_executing_run"] = round(executing_hours, 2)
                result["executing_run_url"] = executed.get("html_url")
                # Health is decided by the EXECUTING run. The bare run age stays in the
                # payload so a reader can see the gap between the two.
                result["healthy"] = executing_hours <= max_age_hours
        results.append(result)
    return results


def _comment_on_tracker(repo: str, issue: int, body: str, token: str) -> None:
    subprocess.run(
        ["gh", "issue", "comment", str(issue), "--repo", repo, "--body", body],
        check=True,
        env={**os.environ, "GH_TOKEN": token},
    )


def comment_unhealthy_trackers(unhealthy: list[dict[str, Any]], token: str) -> None:
    """Post each durable liveness alert in the repository that owns its tracker."""
    for item in unhealthy:
        # An execution_liveness entry has no durable tracker to comment on. It is
        # still reported and still fails the exit code; it just has no issue.
        if item.get("issue") is None:
            continue
        require_step = item.get("require_step")
        executed_lines = ""
        if require_step:
            executed_lines = (
                f"- Required step: `{require_step}`\n"
                f"- Latest run that RAN that step: "
                f"{item.get('latest_executing_created_at') or 'none in recent history'}\n"
                f"- Hours since that run: {item.get('hours_since_executing_run', 'n/a')}\n"
                f"- That run's step conclusion: "
                f"{item.get('required_step_conclusion', 'n/a')}\n"
            )
        body = (
            "## Durable tracker liveness alert\n\n"
            f"Source workflow `{item['workflow']}` latest executable run is outside its "
            f"{item.get('max_age_hours', '?')}h cadence.\n\n"
            f"- Latest executable run: {item.get('latest_created_at', 'none')}\n"
            f"- Held/missed zero-job `action_required` runs: "
            f"{item.get('held_zero_job_run_count', 0)}\n"
            f"- Conclusion: {item.get('latest_conclusion', 'n/a')}\n"
            f"- Hours since: {item.get('hours_since', 'n/a')}\n"
            f"- Run URL: {item.get('run_url', 'n/a')}\n"
            + executed_lines
            + (f"\n{item['reason']}\n" if item.get("reason") else "")
            + "\nConfirm liveness from workflow run history, not tracker comment activity."
        )
        _comment_on_tracker(str(item["repo"]), int(item["issue"]), body, token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "stranske/Workflows"))
    parser.add_argument("--comment-on-failure", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    configured = _durable_tracker_workflows()
    documented = tracker_doc_workflows()
    missing_from_config = sorted(documented - configured)
    extra_in_config = sorted(configured - documented)
    if missing_from_config or extra_in_config:
        print(
            "Tracker workflow coverage mismatch: "
            f"missing_from_config={missing_from_config} extra_in_config={extra_in_config}",
            file=sys.stderr,
        )
        return 2

    token = _github_token()
    results = evaluate_trackers(args.repo, token)
    unhealthy = [item for item in results if not item.get("healthy")]

    if args.json:
        print(json.dumps({"results": results, "unhealthy_count": len(unhealthy)}, indent=2))
    else:
        for item in results:
            status = "healthy" if item.get("healthy") else "UNHEALTHY"
            print(f"{item['workflow']}\t{status}\t{item}")

    if args.comment_on_failure and unhealthy:
        comment_unhealthy_trackers(unhealthy, token)

    return 1 if unhealthy else 0


if __name__ == "__main__":
    raise SystemExit(main())
