#!/usr/bin/env python3
"""Compare a consumer guarded-merge job and inspect its public attempt diagnostics.

Local inputs must come from the same hosted run revision. Hosted collection binds
them to a completed workflow_dispatch or legacy repository_dispatch attempt using
read-only GitHub CLI requests.
Neither mode establishes effective repository permissions or merge success.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import yaml

TEMPLATE = Path("templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml")
LOG_PREFIX = r"^(?:\d{4}-\d{2}-\d{2}T\S+Z )?"
IDENTITY_LINE = re.compile(LOG_PREFIX + r"Guarded merge credential source(?:=|$)")
DIAGNOSTIC = re.compile(
    LOG_PREFIX + r"Guarded merge credential source=(?P<source>[A-Za-z0-9_ .-]+); "
    r"actor=(?P<actor>[A-Za-z0-9][A-Za-z0-9\[\]-]*); OAuth scopes=(?P<scopes>[^\r\n]*)$",
    re.MULTILINE,
)
WORKFLOW_PATH = ".github/workflows/agents-81-gate-followups.yml"


def gh_read(endpoint: str, *, raw: bool = False, paginate: bool = False):
    """Capture API output without printing potentially sensitive response/log data."""
    command = ["gh", "api", "--method", "GET", endpoint]
    if raw:
        command += ["-H", "Accept: application/vnd.github.raw+json"]
    if paginate:
        command += ["--paginate", "--slurp"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=True)
    return result.stdout if raw else json.loads(result.stdout)


def collect_hosted(repo: str, run_id: int, template: str) -> tuple[str, str, dict]:
    """Read one completed dispatch attempt; never dispatch, rerun or mutate a PR."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or run_id <= 0:
        raise ValueError("invalid repository or run id")
    endpoint = f"repos/{repo}/actions/runs/{run_id}"
    run = gh_read(endpoint)
    sha = run.get("head_sha", "")
    attempt = run.get("run_attempt")
    if (
        run.get("id") != run_id
        or run.get("repository", {}).get("full_name", "").lower() != repo.lower()
        or run.get("path") != WORKFLOW_PATH
        or run.get("event") not in ("workflow_dispatch", "repository_dispatch")
        or run.get("status") != "completed"
        or not re.fullmatch(r"[0-9a-f]{40}", sha)
        or type(attempt) is not int
        or attempt <= 0
    ):
        raise ValueError("run does not identify a completed consumer dispatch attempt")
    consumer = gh_read(f"repos/{repo}/contents/{WORKFLOW_PATH}?ref={sha}", raw=True)
    pages = gh_read(f"{endpoint}/attempts/{attempt}/jobs?per_page=100", paginate=True)
    name = guarded_job(template).get("name", "guarded-merge")
    jobs = [job for page in pages for job in page["jobs"] if job.get("name") == name]
    if len(jobs) != 1:
        raise ValueError("run must have exactly one guarded-merge job")
    job = jobs[0]
    if (
        type(job.get("id")) is not int
        or job["id"] <= 0
        or job.get("run_id") != run_id
        or job.get("run_attempt") != attempt
        or job.get("head_sha") != sha
        or job.get("status") != "completed"
        or job.get("conclusion") == "skipped"
    ):
        raise ValueError("guarded-merge job is not bound to the completed attempt")
    # Source drift already blocks deployment verification. Do not let expired or
    # inaccessible logs hide that actionable result behind a generic read error.
    job_matches_source = guarded_job(template) == guarded_job(consumer)
    log = (
        gh_read(f"repos/{repo}/actions/jobs/{job['id']}/logs", raw=True)
        if job_matches_source
        else ""
    )
    if gh_read(endpoint) != run:
        raise ValueError("run changed during collection")
    return (
        consumer,
        log,
        {
            "repo": repo,
            "run_id": run_id,
            "run_attempt": attempt,
            "event": run["event"],
            "head_sha": sha,
            "job_id": job["id"],
            "job_log_collected": job_matches_source,
        },
    )


def guarded_job(text: str) -> dict:
    """Include inherited configuration that selects the job's client and grants.

    Job-level environment and permissions override workflow-level values. In
    particular, comparing the authored job alone misses a changed WRITE_TOKEN
    fallback defined in the workflow environment.
    """
    workflow = yaml.safe_load(text)
    jobs = workflow.get("jobs") if isinstance(workflow, dict) else None
    job = jobs.get("guarded-merge") if isinstance(jobs, dict) else None
    if not isinstance(job, dict) or not job:
        raise ValueError("workflow has no guarded-merge job")
    workflow_env = workflow.get("env", {})
    job_env = job.get("env", {})
    if not isinstance(workflow_env, dict) or not isinstance(job_env, dict):
        raise ValueError("guarded-merge environment must be a mapping")
    return {
        **job,
        "env": {**workflow_env, **job_env},
        # A job's permissions replace the workflow map rather than extending it.
        "permissions": job.get("permissions", workflow.get("permissions")),
    }


def inspect_deployment(template: str, consumer: str, log: str) -> dict:
    """Keep missing scope evidence distinct from an observed classic repo scope.

    Inspect every retry's identity independently. A previous client's repo scope
    cannot establish permissions for the next client. Never retain raw log lines.
    """
    matches = guarded_job(template) == guarded_job(consumer)
    attempts = []
    incomplete_identity = False
    for line in log.splitlines():
        if not IDENTITY_LINE.match(line):
            continue
        diagnostic = DIAGNOSTIC.fullmatch(line)
        if diagnostic is None:
            # A masked or truncated retry cannot inherit an earlier client's
            # identity/scope evidence. Keep raw diagnostic contents out of output.
            incomplete_identity = True
            continue
        scopes = diagnostic["scopes"].strip()
        # Missing fine-grained/App scope headers are unknown, not a denied grant.
        reported = bool(re.fullmatch(r"[A-Za-z0-9_:, -]+", scopes))
        attempts.append(
            {
                "source": diagnostic["source"],
                "actor": diagnostic["actor"],
                "classic_repo_scope_reported": reported
                and "repo" in {scope.strip() for scope in scopes.split(",")},
            }
        )
    blockers = []
    if not matches:
        blockers.append("consumer guarded-merge job differs from selected source")
    if not attempts:
        blockers.append("no merge-client identity diagnostics observed")
    if incomplete_identity:
        blockers.append("one or more merge-client identity diagnostics were incomplete")
    # The actor and repo scope cannot distinguish two PATs owned by one account.
    # Require a named credential/registry key (or github.token), not WRITE_TOKEN's
    # aggregate fallback label. Check each retry independently of earlier clients.
    if any(
        not re.fullmatch(r"(?:[A-Z][A-Z0-9_]*|github\.token)", attempt["source"])
        or attempt["source"] in {"WRITE_TOKEN", "UNKNOWN"}
        for attempt in attempts
    ):
        blockers.append("one or more clients did not identify a specific credential source")
    if any(not attempt["classic_repo_scope_reported"] for attempt in attempts):
        blockers.append("one or more clients require owner permission verification")
    if re.search(
        LOG_PREFIX + r"(?:##\[warning\])?Guarded merge credential identity unavailable: HTTP ",
        log,
        re.MULTILINE,
    ):
        blockers.append("one or more merge-client identities were unavailable")
    return {
        "schema": "guarded-merge-deployment-inspection/v1",
        "job_matches_source": matches,
        "attempts": attempts,
        "blockers": blockers,
        # A scope header alone cannot prove repository access or branch policy.
        "effective_permissions_confirmed": False,
        "merge_success_confirmed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer-workflow", type=Path)
    parser.add_argument("--job-log", type=Path)
    parser.add_argument("--repo", help="Collect a hosted consumer run with gh (read-only)")
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--template", type=Path, default=TEMPLATE)
    args = parser.parse_args(argv)
    hosted = args.repo is not None or args.run_id is not None
    if hosted:
        if not args.repo or args.run_id is None or args.consumer_workflow or args.job_log:
            parser.error("use --repo and --run-id together, without local inputs")
    elif not args.consumer_workflow or not args.job_log:
        parser.error("use --consumer-workflow and --job-log together")
    try:
        template = args.template.read_text(encoding="utf-8")
        if hosted:
            consumer, log, provenance = collect_hosted(args.repo, args.run_id, template)
        else:
            consumer = args.consumer_workflow.read_text(encoding="utf-8")
            log = args.job_log.read_text(encoding="utf-8")
        report = inspect_deployment(template, consumer, log)
        if hosted:
            report["hosted_run"] = provenance
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, yaml.YAMLError):
        # Parser errors may include raw input; omit them from public diagnostics.
        print(json.dumps({"error": "unable to read or parse deployment inputs"}))
        return 2
    print(json.dumps(report, indent=2))
    if not report["job_matches_source"]:
        return 1
    return 2 if report["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
