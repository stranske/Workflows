#!/usr/bin/env python3
"""Compare a consumer guarded-merge job and inspect its public attempt diagnostics.

Inputs must be collected from the same hosted run revision. This read-only check
does not establish provenance, effective repository permissions or merge success.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

TEMPLATE = Path("templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml")
LOG_PREFIX = r"^(?:\d{4}-\d{2}-\d{2}T\S+Z )?"
DIAGNOSTIC = re.compile(
    LOG_PREFIX + r"Guarded merge credential source=(?P<source>[A-Za-z0-9_ .-]+); "
    r"actor=(?P<actor>[A-Za-z0-9][A-Za-z0-9\[\]-]*); OAuth scopes=(?P<scopes>[^\r\n]*)$",
    re.MULTILINE,
)


def guarded_job(text: str) -> dict:
    workflow = yaml.safe_load(text)
    jobs = workflow.get("jobs") if isinstance(workflow, dict) else None
    job = jobs.get("guarded-merge") if isinstance(jobs, dict) else None
    if not isinstance(job, dict) or not job:
        raise ValueError("workflow has no guarded-merge job")
    return job


def inspect_deployment(template: str, consumer: str, log: str) -> dict:
    """Keep missing scope evidence distinct from an observed classic repo scope.

    Inspect every retry's identity independently. A previous client's repo scope
    cannot establish permissions for the next client. Never retain raw log lines.
    """
    matches = guarded_job(template) == guarded_job(consumer)
    attempts = []
    for diagnostic in DIAGNOSTIC.finditer(log):
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
    parser.add_argument("--consumer-workflow", type=Path, required=True)
    parser.add_argument("--job-log", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=TEMPLATE)
    args = parser.parse_args(argv)
    try:
        report = inspect_deployment(
            args.template.read_text(encoding="utf-8"),
            args.consumer_workflow.read_text(encoding="utf-8"),
            args.job_log.read_text(encoding="utf-8"),
        )
    except (OSError, ValueError, yaml.YAMLError):
        # Parser errors may include raw input; omit them from public diagnostics.
        print(json.dumps({"error": "unable to read or parse deployment inputs"}))
        return 2
    print(json.dumps(report, indent=2))
    if not report["job_matches_source"]:
        return 1
    return 2 if report["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
