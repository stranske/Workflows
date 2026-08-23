#!/usr/bin/env python3
"""Diagnose zero-job workflow startup failures and approval holds.

Two modes:

* ``--run-id`` diagnoses one run (parse-time startup failures, approval holds).
* ``--sweep`` walks every workflow in one or more repositories and reports the
  ones whose recent runs are dominated by zero-job ``action_required`` holds.
  This is the executable form of the liveness oracle in
  ``docs/ops/DURABLE_TRACKING_ISSUES.md``: confirm liveness from the workflow
  run history, not from tracker activity. A held workflow emits no jobs, no
  logs, no annotations and burns no minutes, so nothing else notices it.

The sweep always reports the blocking quantity AND the drainable quantity in
the same line. "12 held" reads as a backlog to work through; "12 held, 0
clearable by API" reads as a deadlock. The drainable count is measured per
run (fork-PR holds accept the REST approval endpoint; unproven-workflow holds
do not), never assumed.

The sweep reports and fails. It must never approve a run: auto-approving a
hold GitHub raised on suspicion of malice would turn a safety mechanism into a
rubber stamp.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from typing import Any

from scripts import api_client


def _github_token() -> str:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    result = subprocess.run(["gh", "auth", "token"], check=True, capture_output=True, text=True)
    return result.stdout.strip()


# GitHub enforces a SECONDARY rate limit on rapid sequential requests, separate
# from the hourly quota and invisible to /rate_limit - it answers 403 with a
# "rate limit" message while /rate_limit still reports thousands remaining. A
# repo-wide sweep is ~1 call per workflow, which trips it. Two defences:
#
#   * pace requests, so the burst threshold is not reached; and
#   * retry with a backoff long enough to matter. api_client already recognises
#     the 403, but its defaults (3 attempts, 1s backoff) give up after ~3 seconds
#     when a secondary limit wants a minute or more.
#
# Without both, the daily liveness job dies on its own API usage - a detector
# that cannot survive its own traffic reports nothing, which is the failure this
# whole module exists to prevent.
_PACE_SECONDS = float(os.environ.get("WORKFLOW_SWEEP_PACE_SECONDS", "0.12"))
_RETRY_ATTEMPTS = int(os.environ.get("WORKFLOW_SWEEP_RETRY_ATTEMPTS", "6"))
_RETRY_BACKOFF = float(os.environ.get("WORKFLOW_SWEEP_RETRY_BACKOFF", "8"))


def _pace() -> None:
    if _PACE_SECONDS > 0:
        time.sleep(_PACE_SECONDS)


def _get_json(path: str, token: str | None = None) -> Any:
    auth_token = token or _github_token()
    _pace()
    return api_client._request_json(
        "GET",
        f"{api_client.GITHUB_API}/{path.lstrip('/')}",
        auth_token,
        payload=None,
        max_attempts=_RETRY_ATTEMPTS,
        backoff=_RETRY_BACKOFF,
    )


def _gh_api(path: str, token: str | None = None) -> dict[str, Any]:
    data = _get_json(path, token)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object from GitHub API path {path}")
    return data


def _gh_api_list(path: str, token: str | None = None) -> list[Any]:
    """GET a path whose success body is a JSON array.

    ``_gh_api`` raises on anything that is not an object, so routing the commits
    endpoint through it turns every review into a ValueError that aborts the whole
    sweep. Returns [] for an object, which is what an error body looks like -
    callers must treat [] as "could not determine", never as "nothing found".
    """
    data = _get_json(path, token)
    return data if isinstance(data, list) else []


def _collect_startup_failures(
    check_runs_payload: dict[str, Any], run_id: int
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    check_runs = check_runs_payload.get("check_runs", [])
    if not isinstance(check_runs, list):
        return matches

    run_marker = f"/actions/runs/{run_id}"
    for check in check_runs:
        if not isinstance(check, dict):
            continue
        if check.get("conclusion") != "startup_failure":
            continue
        details_url = str(check.get("details_url", ""))
        if run_marker not in details_url:
            continue
        matches.append(check)
    return matches


def diagnose_startup_failure(repo: str, run_id: int) -> dict[str, Any]:
    run_payload = _gh_api(f"repos/{repo}/actions/runs/{run_id}")
    jobs_payload = _gh_api(f"repos/{repo}/actions/runs/{run_id}/jobs")

    head_sha = str(run_payload.get("head_sha", "")).strip()
    if not head_sha:
        raise ValueError(f"Run {run_id} in {repo} is missing head_sha")

    check_runs_payload = _gh_api(f"repos/{repo}/commits/{head_sha}/check-runs")
    startup_failures = _collect_startup_failures(check_runs_payload, run_id)

    findings: list[dict[str, Any]] = []
    for check in startup_failures:
        output = check.get("output") if isinstance(check.get("output"), dict) else {}
        summary = str(output.get("summary", ""))
        title = str(output.get("title", ""))
        text = str(output.get("text", ""))
        phase, suspected_root_cause = _classify_startup_failure(
            summary=summary,
            title=title,
            text=text,
        )
        findings.append(
            {
                "id": check.get("id"),
                "name": check.get("name"),
                "status": check.get("status"),
                "conclusion": check.get("conclusion"),
                "started_at": check.get("started_at"),
                "completed_at": check.get("completed_at"),
                "details_url": check.get("details_url"),
                "html_url": check.get("html_url"),
                "title": title,
                "summary": summary,
                "text": text,
                "failure_phase": phase,
                "suspected_root_cause": suspected_root_cause,
            }
        )

    jobs = jobs_payload.get("jobs", [])
    jobs_count = len(jobs) if isinstance(jobs, list) else 0
    approval_hold = None
    if run_payload.get("conclusion") == "action_required" and jobs_count == 0:
        approval_hold = _classify_zero_job_approval_hold(repo, run_id, run_payload)
    return {
        "repo": repo,
        "run_id": run_id,
        "run_name": run_payload.get("name", ""),
        "run_conclusion": run_payload.get("conclusion", ""),
        "run_status": run_payload.get("status", ""),
        "head_sha": head_sha,
        "jobs_count": jobs_count,
        "approval_hold": approval_hold,
        "startup_failures": findings,
    }


def _head_repository_is_fork(repo: str, run_payload: dict[str, Any]) -> bool | None:
    """Return True/False when fork status is known; None when it cannot be told."""
    head_repo = run_payload.get("head_repository")
    if not isinstance(head_repo, dict):
        return None
    if "fork" in head_repo:
        return bool(head_repo.get("fork"))
    head_full = str(head_repo.get("full_name") or "").strip()
    if not head_full:
        return None
    return head_full.lower() != repo.lower()


def _classify_zero_job_approval_hold(
    repo: str, run_id: int, run_payload: dict[str, Any]
) -> dict[str, str]:
    """Distinguish fork-PR REST-approvable holds from unproven-workflow web holds."""
    approval_url = f"https://github.com/{repo}/actions/runs/{run_id}"
    event = str(run_payload.get("event") or "").strip()
    is_fork = _head_repository_is_fork(repo, run_payload)

    if event == "pull_request" and is_fork is True:
        return {
            "failure_phase": "pre_job_workflow_approval",
            "suspected_root_cause": "fork_contributor_approval_hold",
            "approval_url": approval_url,
            "remediation": (
                "Public-fork pull-request runs awaiting contributor approval can be "
                "recovered with POST /repos/{owner}/{repo}/actions/runs/{run_id}/approve "
                "(or Approve and run in the GitHub UI)."
            ),
        }

    if event == "pull_request" and is_fork is None:
        return {
            "failure_phase": "pre_job_workflow_approval",
            "suspected_root_cause": "workflow_approval_hold_unspecified",
            "approval_url": approval_url,
            "remediation": (
                "Zero-job action_required on a pull_request run: inspect event and "
                "head_repository.fork before choosing remediation. Fork contributor "
                "holds accept the workflow-run approval REST endpoint; unproven-workflow "
                "holds require Approve and run in an authenticated GitHub web session."
            ),
        }

    return {
        "failure_phase": "pre_job_workflow_approval",
        "suspected_root_cause": "github_unproven_workflow_protection",
        "approval_url": approval_url,
        "remediation": (
            "Review the workflow file, then use Approve and run from an "
            "authenticated GitHub web session. The workflow-run approval "
            "REST endpoint does not cover this protection."
        ),
    }


DRAINABLE_ROOT_CAUSES = frozenset({"fork_contributor_approval_hold"})

HELD_RUN_CONCLUSION = "action_required"


def _iter_paginated(
    path: str, key: str, token: str, per_page: int = 100, max_pages: int = 20
) -> list[dict[str, Any]]:
    """Collect ``key`` entries across pages. Stops on the first short page."""
    items: list[dict[str, Any]] = []
    joiner = "&" if "?" in path else "?"
    for page in range(1, max_pages + 1):
        payload = _gh_api(f"{path}{joiner}per_page={per_page}&page={page}", token)
        batch = payload.get(key, [])
        if not isinstance(batch, list) or not batch:
            break
        items.extend(x for x in batch if isinstance(x, dict))
        if len(batch) < per_page:
            break
    return items


def _days_between(earlier: str, later: str) -> int | None:
    """Whole days between two GitHub ISO-8601 timestamps."""
    from datetime import datetime

    try:
        a = datetime.fromisoformat(earlier.replace("Z", "+00:00"))
        b = datetime.fromisoformat(later.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, (b - a).days)


def _utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _find_hold_onset(
    repo: str, workflow_id: Any, token: str, max_pages: int = 10
) -> tuple[int, str | None, bool, str | None]:
    """Walk back to the newest run that actually executed.

    Returns ``(consecutive_held, onset, truncated, last_healthy)``. The streak routinely
    exceeds one page: a workflow triggered hourly discards 20 runs in under a
    day, so reading the onset off a single sample page reports a three-week
    outage as hours old - which is the same silence this sweep exists to break.
    ``truncated`` means the streak outran ``max_pages``, so the onset is a lower
    bound rather than the real one.

    ``last_healthy`` is the timestamp of the run that broke the streak - the newest
    run that actually executed. It falls out of this walk for free, so the review
    must not re-paginate the same pages to find it: that doubled the API cost of
    every held workflow, and this sweep spends the installation token the whole
    fleet shares.
    """
    streak = 0
    onset: str | None = None
    for page in range(1, max_pages + 1):
        payload = _gh_api(
            f"repos/{repo}/actions/workflows/{workflow_id}/runs?per_page=100&page={page}",
            token,
        )
        runs = payload.get("workflow_runs", [])
        if not isinstance(runs, list) or not runs:
            return streak, onset, False, None
        for run in runs:
            if not isinstance(run, dict) or run.get("conclusion") != HELD_RUN_CONCLUSION:
                healthy = str((run or {}).get("created_at") or "").strip() or None
                return streak, onset, False, healthy
            streak += 1
            created = str(run.get("created_at") or "").strip()
            if created:
                onset = created
        if len(runs) < 100:
            return streak, onset, False, None
    return streak, onset, True, None


# Additions a reviewer must actually look at before approving a held workflow.
# GitHub's banner asks a human to review the file; these are the shapes worth a
# human's attention. Everything else (a dependency pin bump, a log string) is
# what the review is trying NOT to spend time on.
REVIEW_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\$\{\{[^}]*(?:github\.event|inputs)\.", "event/input interpolated into a body"),
    (r"\b(?:curl|wget)\b", "network fetch"),
    (r"\|\s*(?:bash|sh)\b", "pipe to shell"),
    (r"base64\s+-d", "base64 decode"),
    (r"uses:\s*(?!\./|actions/|github/)\S", "third-party action"),
    (r"^\s*permissions:", "permissions change"),
)


def review_hold(
    repo: str, workflow_path: str, since: str | None, token: str, max_commits: int = 3
) -> dict[str, Any]:
    """Summarise what changed in a held workflow file since it last executed.

    This is the expensive half of clearing a hold. The click takes seconds; working
    out whether the file is safe to approve is what costs minutes, and it is
    mechanical. Doing it here turns the human step into "read the verdict, click".

    A verdict of ``benign`` means no addition matched REVIEW_PATTERNS. It is an aid
    to a human decision, never an authorisation - nothing in this module approves
    anything.
    """
    if not since:
        return {"verdict": "unknown", "reason": "no healthy run in range", "commits": []}
    encoded = workflow_path.replace("#", "%23")
    try:
        commits = _gh_api_list(
            f"repos/{repo}/commits?path={encoded}&since={since}&per_page={max_commits}", token
        )
    except (ValueError, OSError):
        # A failed lookup must not read as reassuring: "benign" for a file nobody
        # managed to inspect is exactly the plausible-but-wrong output this sweep
        # exists to remove.
        return {"verdict": "unknown", "reason": "commit lookup failed", "commits": []}
    if not commits:
        return {"verdict": "no-edit", "reason": "no commit touched the file", "commits": []}

    findings: set[str] = set()
    seen = []
    for commit in commits[:max_commits]:
        sha = str(commit.get("sha") or "")
        detail = _gh_api(f"repos/{repo}/commits/{sha}", token)
        files = detail.get("files") if isinstance(detail, dict) else None
        patch = ""
        if isinstance(files, list):
            for entry in files:
                if isinstance(entry, dict) and entry.get("filename") == workflow_path:
                    patch = str(entry.get("patch") or "")
                    break
        added = [
            line[1:]
            for line in patch.split("\n")
            if line.startswith("+") and not line.startswith("+++")
        ]
        hits = {
            label
            for line in added
            for pattern, label in REVIEW_PATTERNS
            if re.search(pattern, line)
        }
        findings |= hits
        message = str((commit.get("commit") or {}).get("message") or "").split("\n")[0]
        seen.append({"sha": sha[:8], "subject": message[:60], "findings": sorted(hits)})

    return {
        "verdict": "needs-eyes" if findings else "benign",
        "reason": ", ".join(sorted(findings)) if findings else "no risky additions",
        "commits": seen,
    }


def sweep_repository(
    repo: str,
    token: str,
    sample: int = 20,
    threshold: float = 0.0,
    min_runs: int = 1,
    now: str | None = None,
    review: bool = True,
) -> dict[str, Any]:
    """Report workflows in ``repo`` whose recent history is dominated by holds.

    A workflow is held when at least ``min_runs`` runs were sampled and the held
    share reaches ``threshold``. The newest held run is confirmed to have zero
    jobs, which is what separates this class from a deployment-approval gate.
    """
    workflows = _iter_paginated(f"repos/{repo}/actions/workflows", "workflows", token)
    held: list[dict[str, Any]] = []
    scanned = 0

    for workflow in workflows:
        workflow_id = workflow.get("id")
        if workflow_id is None or workflow.get("state") != "active":
            continue
        path = str(workflow.get("path") or "")
        if not path.startswith(".github/workflows/"):
            continue
        scanned += 1

        payload = _gh_api(
            f"repos/{repo}/actions/workflows/{workflow_id}/runs?per_page={sample}", token
        )
        runs = [r for r in payload.get("workflow_runs", []) if isinstance(r, dict)]
        if len(runs) < min_runs:
            continue

        # "Held" means "blocked right now", and deciding that needs care in two
        # directions, both learned the hard way.
        #
        # Judging the held SHARE of the sample reports a workflow that has already
        # recovered, because history dominates the window for a long outage.
        #
        # Judging only runs[0] is also wrong. Approving a run marks that workflow
        # FILE VERSION trusted going FORWARD; it does not retroactively release
        # runs already created. So a burst of runs from one moment leaves stale
        # held siblings behind after the approval, and the newest by created_at can
        # be one of them while the workflow is perfectly healthy for new events.
        # Observed exactly this: three workflows whose approved runs went to
        # attempt 2 and executed, while same-second siblings stayed at attempt 1.
        #
        # The honest test: is there any run at or after the newest held run that
        # actually executed? If so, the file version is trusted and new events will
        # run.
        held_runs = [r for r in runs if r.get("conclusion") == HELD_RUN_CONCLUSION]
        if not held_runs:
            continue
        newest_held_at = str(held_runs[0].get("created_at") or "")
        executed_after = [
            r
            for r in runs
            if r.get("conclusion") != HELD_RUN_CONCLUSION
            and str(r.get("created_at") or "") >= newest_held_at
        ]
        if executed_after:
            continue
        if threshold and len(held_runs) / len(runs) < threshold:
            continue

        newest = held_runs[0]
        run_id = newest.get("id")
        jobs_payload = _gh_api(f"repos/{repo}/actions/runs/{run_id}/jobs", token)
        jobs = jobs_payload.get("jobs", [])
        if isinstance(jobs, list) and jobs:
            # Jobs exist, so this is a deployment/environment gate, not the
            # zero-job protection hold this sweep exists to surface.
            continue

        classification = _classify_zero_job_approval_hold(repo, int(run_id), newest)
        streak, onset, truncated, last_healthy = _find_hold_onset(repo, workflow_id, token)
        reference = now or _utc_now_iso()
        assessment: dict[str, Any] = {"verdict": "skipped", "reason": "review disabled"}
        if review:
            assessment = review_hold(repo, path, last_healthy, token)
        held.append(
            {
                "repo": repo,
                "workflow": path,
                "name": workflow.get("name"),
                "held_runs_sampled": len(held_runs),
                "runs_sampled": len(runs),
                "consecutive_held": streak,
                "onset": onset,
                "onset_truncated": truncated,
                "days_held": _days_between(onset, reference) if onset else None,
                "newest_held_run": run_id,
                "suspected_root_cause": classification["suspected_root_cause"],
                "drainable_by_api": classification["suspected_root_cause"] in DRAINABLE_ROOT_CAUSES,
                "approval_url": classification["approval_url"],
                "remediation": classification["remediation"],
                "review": assessment,
            }
        )

    return {"repo": repo, "workflows_scanned": scanned, "held": held}


def sweep(
    repos: list[str],
    token: str | None = None,
    sample: int = 20,
    threshold: float = 0.0,
    min_runs: int = 1,
    now: str | None = None,
    review: bool = True,
) -> dict[str, Any]:
    """Sweep every repository and aggregate the blocking/drainable pair."""
    auth = token or _github_token()
    repo_reports = [
        sweep_repository(
            repo,
            auth,
            sample=sample,
            threshold=threshold,
            min_runs=min_runs,
            now=now,
            review=review,
        )
        for repo in repos
    ]
    held = [h for report in repo_reports for h in report["held"]]
    drainable = [h for h in held if h["drainable_by_api"]]
    oldest = None
    for entry in held:
        if entry["days_held"] is None:
            continue
        if oldest is None or entry["days_held"] > oldest["days_held"]:
            oldest = entry
    return {
        "repos": repos,
        "workflows_scanned": sum(r["workflows_scanned"] for r in repo_reports),
        "held_count": len(held),
        "benign_count": sum(1 for h in held if h.get("review", {}).get("verdict") == "benign"),
        "needs_eyes_count": sum(
            1 for h in held if h.get("review", {}).get("verdict") == "needs-eyes"
        ),
        "drainable_count": len(drainable),
        "held_runs_discarded": sum(h["consecutive_held"] for h in held),
        "oldest_hold": oldest,
        "held": held,
        "per_repo": [
            {"repo": r["repo"], "workflows_scanned": r["workflows_scanned"], "held": len(r["held"])}
            for r in repo_reports
        ],
    }


def _fmt_days(entry: dict[str, Any]) -> str:
    """Render days-held without ever printing a bare None."""
    days = entry.get("days_held")
    if days is None:
        return "age unknown"
    return f"{'>=' if entry.get('onset_truncated') else ''}{days}d"


def format_sweep_summary(report: dict[str, Any]) -> str:
    """One line carrying the blocking quantity and the drainable quantity.

    Printed on green runs too, so a passing sweep always states what it checked.
    """
    held = report["held_count"]
    drainable = report["drainable_count"]
    scanned = report["workflows_scanned"]
    if not held:
        return f"workflow liveness: 0 held / {scanned} active workflows scanned - all executing"
    oldest = report["oldest_hold"]
    tail = ""
    if oldest:
        prefix = ">=" if oldest["onset_truncated"] else ""
        tail = (
            f"; oldest {prefix}{oldest['days_held']}d " f"({oldest['workflow'].rsplit('/', 1)[-1]})"
        )
    remedy = "web approval required" if drainable < held else "REST approval available"
    triage = ""
    if report.get("needs_eyes_count") or report.get("benign_count"):
        triage = (
            f"; {report.get('benign_count', 0)} benign, "
            f"{report.get('needs_eyes_count', 0)} need eyes"
        )
    return (
        f"workflow liveness: {held} held / {drainable} clearable by API - {remedy}"
        f"{tail}{triage}; {report['held_runs_discarded']} runs discarded; "
        f"{scanned} active workflows scanned"
    )


def _classify_startup_failure(summary: str, title: str, text: str) -> tuple[str, str]:
    """Best-effort classification for parse-time startup failures."""
    blob = "\n".join((title, summary, text)).lower()
    if "workflow is not valid" in blob or "line " in blob:
        return ("workflow_parse_or_graph", _guess_parse_cause(blob))
    if "unable to resolve action" in blob or "repository not found" in blob:
        return ("action_resolution", "action_reference_or_access")
    return ("unknown", "unknown")


def _guess_parse_cause(blob: str) -> str:
    if "unrecognized named-value" in blob:
        return "invalid_expression_context_reference"
    if re.search(r"unexpected value|mapping values are not allowed", blob):
        return "yaml_structure_or_syntax"
    if "fromjson" in blob and "invalid" in blob:
        return "expression_type_or_json_coercion"
    return "workflow_parse_or_job_graph_construction"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="Repository in owner/name format")
    parser.add_argument("--run-id", type=int, help="Workflow run ID (single-run mode)")
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Sweep every active workflow for zero-job action_required holds",
    )
    parser.add_argument(
        "--repos",
        default="",
        help="Comma-separated extra repositories to include in the sweep",
    )
    parser.add_argument("--sample", type=int, default=20, help="Runs sampled per workflow")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help=(
            "Optional extra filter: minimum held share of the sampled runs. "
            "Held is decided by the newest run; this only suppresses noise."
        ),
    )
    parser.add_argument(
        "--min-runs", type=int, default=1, help="Minimum sampled runs before judging a workflow"
    )
    parser.add_argument(
        "--no-review",
        action="store_true",
        help="Skip the per-hold diff review (fewer API calls, less useful output)",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Exit 0 even when holds are found (sweep mode)",
    )
    return parser


def _sweep_repos(args: argparse.Namespace) -> list[str]:
    repos = [args.repo] if args.repo else []
    repos += [r.strip() for r in str(args.repos or "").split(",") if r.strip()]
    seen: set[str] = set()
    ordered: list[str] = []
    for repo in repos:
        if repo not in seen:
            seen.add(repo)
            ordered.append(repo)
    return ordered


def _run_sweep(args: argparse.Namespace) -> int:
    repos = _sweep_repos(args)
    if not repos:
        print(
            "workflow_startup_failure_diagnostic: --sweep needs --repo and/or --repos",
            file=sys.stderr,
        )
        return 1
    report = sweep(
        repos,
        sample=args.sample,
        threshold=args.threshold,
        min_runs=args.min_runs,
        review=not args.no_review,
    )
    summary = format_sweep_summary(report)
    print(summary)
    for entry in report["held"]:
        print(
            f"  HELD {entry['repo']} {entry['workflow']}"
            f" - {entry['consecutive_held']} consecutive held runs,"
            f" {_fmt_days(entry)},"
            f" review={entry.get('review', {}).get('verdict', '?')}"
            f" ({entry.get('review', {}).get('reason', '')})"
            f" -> {entry['approval_url']}"
        )
    print(json.dumps(report, indent=2))
    _write_step_summary(summary, report)
    if report["held_count"] and not args.report_only:
        return 1
    return 0


def _write_step_summary(summary: str, report: dict[str, Any]) -> None:
    """Mirror the sweep verdict into the Actions step summary when present."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [f"### Workflow liveness sweep\n\n{summary}\n"]
    if report["held"]:
        lines.append(
            "\n| repo | workflow | held | days | review | why | approve |\n"
            "|---|---|---|---|---|---|---|\n"
        )
        for entry in report["held"]:
            lines.append(
                f"| {entry['repo']} | `{entry['workflow'].rsplit('/', 1)[-1]}` |"
                f" {entry['consecutive_held']} |"
                f" {_fmt_days(entry)} |"
                f" **{entry.get('review', {}).get('verdict', '?')}** |"
                f" {entry.get('review', {}).get('reason', '')} |"
                f" [approve]({entry['approval_url']}) |\n"
            )
        lines.append(
            "\nNo REST endpoint clears an unproven-workflow hold. Use **Approve and "
            "run** in an authenticated web session; this sweep never approves.\n"
        )
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("".join(lines))
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.sweep:
        try:
            return _run_sweep(args)
        except (subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as exc:
            print(f"workflow_startup_failure_diagnostic: {exc}", file=sys.stderr)
            return 1

    if not args.repo or args.run_id is None:
        parser.error("--repo and --run-id are required unless --sweep is given")

    try:
        report = diagnose_startup_failure(args.repo, args.run_id)
    except (subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as exc:
        print(f"workflow_startup_failure_diagnostic: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2))
    if report["approval_hold"]:
        return 0
    if report["jobs_count"] == 0 and report["startup_failures"]:
        return 0
    if report["startup_failures"]:
        return 0
    print(
        "No matching startup_failure check-runs or zero-job approval hold found " "for this run.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
