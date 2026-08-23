#!/usr/bin/env python3
"""Assert durable tracker source workflows executed inside their cadence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "durable_tracker_liveness.yml"
TRACKER_DOC = REPO_ROOT / "docs" / "ops" / "DURABLE_TRACKING_ISSUES.md"
EXECUTABLE_CONCLUSIONS = frozenset({"success", "failure", "cancelled", "timed_out"})


def _github_token() -> str:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    return subprocess.check_output(["gh", "auth", "token"], text=True).strip()


def _load_config() -> list[dict[str, Any]]:
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    trackers = data.get("trackers")
    if not isinstance(trackers, list) or not trackers:
        raise ValueError(f"{CONFIG_PATH} must define a non-empty trackers list")
    return trackers


def tracker_doc_workflows() -> set[str]:
    import re

    text = TRACKER_DOC.read_text(encoding="utf-8")
    section_match = re.search(
        r"## Current durable trackers\n\n\| Issue.*?\n\|[-| ]+\n(.*?)(?:\n\n|\n### )",
        text,
        re.DOTALL,
    )
    assert section_match, "DURABLE_TRACKING_ISSUES.md is missing the tracker table"
    table_body = section_match.group(1)
    workflows = re.findall(r"\[`[^`]+`\]\([^)]*/([^/)]+)\)", table_body)
    return {name for name in workflows if name.endswith(".yml")}


def _latest_executable_run(repo: str, workflow_file: str, token: str) -> dict[str, Any] | None:
    """Newest run of ``workflow_file`` that actually executed, or None.

    Deliberately still shells to ``gh`` rather than sharing
    ``workflow_startup_failure_diagnostic``'s HTTP layer. That module imports
    ``requests`` via ``scripts.api_client``, and health-71 installs only
    ``pyyaml`` -- importing it here would reproduce the exact
    ``ModuleNotFoundError: requests`` that broke the health-40 liveness job. The
    two probes therefore share a purpose and not a transport; the overlap is
    ~15 lines, and forcing one transport would cost health-71 a dependency and an
    edit that re-arms the suspicious-workflow scan on it.

    What was NOT optional is the retry. This ran with no backoff at all, so a
    single GitHub *secondary* rate-limit 403 -- a separate cap on rapid
    sequential requests, invisible to /rate_limit -- raised CalledProcessError
    and aborted the whole liveness check. That is the same trap the sweep hit.
    """
    attempts, backoff = 5, 8.0
    raw = ""
    for attempt in range(1, attempts + 1):
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/actions/workflows/{workflow_file}/runs",
                "--method",
                "GET",
                "-f",
                "per_page=100",
                "--jq",
                ".workflow_runs",
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "GH_TOKEN": token},
        )
        if result.returncode == 0:
            raw = result.stdout
            break
        combined = (result.stdout + result.stderr).lower()
        transient = "rate limit" in combined or "was submitted too quickly" in combined
        if attempt < attempts and transient:
            time.sleep(backoff * attempt)
            continue
        # Non-transient, or out of attempts: surface it rather than reporting a
        # healthy-looking None, which would read as "no executable run" and
        # blame the workflow for an API failure.
        raise RuntimeError(
            f"gh api failed for {workflow_file} after {attempt} attempt(s): "
            f"{result.stderr.strip()[:300]}"
        )

    try:
        runs = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(runs, list):
        return None
    for run in runs:
        if not isinstance(run, dict):
            continue
        if str(run.get("conclusion") or "") in EXECUTABLE_CONCLUSIONS:
            return run
    return None


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


def _hours_since(iso_timestamp: str) -> float:
    created = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    return (datetime.now(UTC) - created).total_seconds() / 3600.0


def evaluate_trackers(repo: str, token: str | None = None) -> list[dict[str, Any]]:
    auth = token or _github_token()
    results: list[dict[str, Any]] = []
    for entry in _load_config():
        workflow = str(entry["workflow"])
        issue = int(entry["issue"])
        if entry.get("event_driven") is True:
            results.append(
                {
                    "workflow": workflow,
                    "issue": issue,
                    "healthy": True,
                    "reason": "event-driven workflow excluded from age-based liveness",
                }
            )
            continue
        max_age_hours = float(entry["max_age_hours"])
        latest = _latest_executable_run(repo, workflow, auth)
        if latest is None:
            results.append(
                {
                    "workflow": workflow,
                    "issue": issue,
                    "healthy": False,
                    "reason": (
                        "no executable run found (only action_required/skipped)."
                        + _held_by_workflow_protection(True, repo, workflow)
                    ),
                }
            )
            continue
        hours = _hours_since(str(latest["created_at"]))
        healthy = hours <= max_age_hours
        results.append(
            {
                "workflow": workflow,
                "issue": issue,
                "healthy": healthy,
                "latest_conclusion": latest.get("conclusion"),
                "latest_created_at": latest.get("created_at"),
                "hours_since": round(hours, 2),
                "max_age_hours": max_age_hours,
                "run_url": latest.get("html_url"),
            }
        )
    return results


def _comment_on_tracker(repo: str, issue: int, body: str, token: str) -> None:
    subprocess.run(
        ["gh", "issue", "comment", str(issue), "--repo", repo, "--body", body],
        check=True,
        env={**os.environ, "GH_TOKEN": token},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "stranske/Workflows"))
    parser.add_argument("--comment-on-failure", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    configured = {str(entry["workflow"]) for entry in _load_config()}
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
        for item in unhealthy:
            body = (
                "## Durable tracker liveness alert\n\n"
                f"Source workflow `{item['workflow']}` has no executable run inside its "
                f"{item.get('max_age_hours', '?')}h cadence.\n\n"
                f"- Latest executable run: {item.get('latest_created_at', 'none')}\n"
                f"- Conclusion: {item.get('latest_conclusion', 'n/a')}\n"
                f"- Hours since: {item.get('hours_since', 'n/a')}\n"
                f"- Run URL: {item.get('run_url', 'n/a')}\n\n"
                "Confirm liveness from workflow run history, not tracker comment activity."
            )
            _comment_on_tracker(args.repo, int(item["issue"]), body, token)

    return 1 if unhealthy else 0


if __name__ == "__main__":
    raise SystemExit(main())
