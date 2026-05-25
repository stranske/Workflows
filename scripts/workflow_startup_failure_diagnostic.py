#!/usr/bin/env python3
"""Capture startup_failure details for a workflow run via GitHub check-runs."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any

from scripts import api_client


def _github_token() -> str:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    result = subprocess.run(["gh", "auth", "token"], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _gh_api(path: str, token: str | None = None) -> dict[str, Any]:
    auth_token = token or _github_token()
    data = api_client._request_json(
        "GET",
        f"{api_client.GITHUB_API}/{path.lstrip('/')}",
        auth_token,
        payload=None,
    )
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object from GitHub API path {path}")
    return data


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
    return {
        "repo": repo,
        "run_id": run_id,
        "run_name": run_payload.get("name", ""),
        "run_conclusion": run_payload.get("conclusion", ""),
        "run_status": run_payload.get("status", ""),
        "head_sha": head_sha,
        "jobs_count": jobs_count,
        "startup_failures": findings,
    }


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
    parser.add_argument("--repo", required=True, help="Repository in owner/name format")
    parser.add_argument("--run-id", required=True, type=int, help="Workflow run ID")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        report = diagnose_startup_failure(args.repo, args.run_id)
    except (subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as exc:
        print(f"workflow_startup_failure_diagnostic: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2))
    if report["jobs_count"] == 0 and report["startup_failures"]:
        return 0
    if report["startup_failures"]:
        return 0
    print("No matching startup_failure check-runs found for this run.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
