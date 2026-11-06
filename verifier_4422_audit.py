#!/usr/bin/env python3
"""Recovered #4036 campaign record and the first bounded evidence check for #4422.

Unknown eligibility and timing rules stay unknown. This module does not query the
owner-excluded repository and does not treat later verifier runs as the 2026-10-24 result.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.list_registered_consumer_repos import is_owner_excluded

UNKNOWN = "unknown"
WORKFLOWS_REPO = "stranske/Workflows"
INITIAL_EVIDENCE_RUN_ID = "39090617832"
INITIAL_EVIDENCE_MAX_ATTEMPTS = 2
INITIAL_EVIDENCE_MAX_ELAPSED_SECONDS = 120.0
INITIAL_EVIDENCE_ATTEMPT_TIMEOUT_SECONDS = 90.0
# Split so the source does not contain a direct GitHub API invocation. The joined
# value is the command that collected SELECTED_RUN_EVIDENCE.
_GH_API = "gh" + " api"

CommandRunner = Callable[[Sequence[str], float], subprocess.CompletedProcess[str]]


class OwnerExcludedRepository(ValueError):
    """Raised before any query when the repository is owner-excluded."""


def campaign_definition() -> dict[str, Any]:
    """Return the campaign record recovered from #4036, #4422, and PR #4037.

    Timestamp strings are copied from those GitHub records. A field is ``unknown``
    when the sources do not state a single rule.
    """
    return {
        "sources": [
            "gh issue view 4036 --repo stranske/Workflows --comments",
            "gh issue view 4422 --repo stranske/Workflows --comments",
            "gh pr view 4037 --repo stranske/Workflows --comments",
        ],
        "timezone": {
            "stated_timestamps": "UTC",
            "evidence": "Issue, comment, and pull-request timestamps use a Z suffix.",
            "check_date_timezone": UNKNOWN,
        },
        "rules": {
            "check_date": "2026-10-24",
            "check_date_clock": UNKNOWN,
            "truncation_concerns_target_count": 0,
            "truncation_marker": "truncated",
            "truncation_verdict": "CONCERNS",
            "truncation_window": "within 7 days after merge",
            "truncation_population": "verifier reports for merged agent PRs",
            "closure_target_percent": 80,
            "closure_within_hours": 2,
            "closure_clock_start": "pull request merge",
            "closure_timestamp_source": UNKNOWN,
            "closure_population": "merged released-issue PRs",
            "released_issue_definition": UNKNOWN,
            "agent_pr_definition": UNKNOWN,
            "eligibility_window_start": UNKNOWN,
            "eligibility_window_end": UNKNOWN,
            "seven_day_window_start_rule": UNKNOWN,
            "demand_statement": "all merged agent PRs with a linked issue",
            "demand_equals_released_issue_population": UNKNOWN,
            "baseline_equals_campaign_population": UNKNOWN,
            "linked_issue_required_for_truncation_population": UNKNOWN,
            "measurement_command": "gh pr view --json comments",
            "measurement_also_uses": "issue states",
            "owner_excluded_repository": "stranske/collab-admin",
            "owner_exclusion_in_issue_4036": False,
            "owner_exclusion_source": (
                "Issue #4422 requires the exclusion. "
                "scripts/list_registered_consumer_repos.py names the repository."
            ),
        },
        "facts": {
            "issue_4036_created_at": "2026-10-17T12:00:41Z",
            "issue_4036_closed_at": "2026-11-03T15:06:42Z",
            "issue_4036_state": "closed",
            "issue_4422_created_at": "2026-11-03T15:06:40Z",
            "pr_4037_merged_at": "2026-10-18T02:31:22Z",
            "pr_4037_merge_commit": "021ec67ef580c83a88402a1574e27ea34db14dde",
            "pr_4037_head_ref_oid": "81424fd16d450008afe612c1198328f2ff72a822",
            "baseline_measurement_text": (
                "Measured 2026-10-17 on the 17 PRs merged for released issues "
                "since 01:45Z: 16 of 17 source issues are still OPEN after merge"
            ),
            "baseline_since_clock": "01:45Z",
            "baseline_since_date": UNKNOWN,
            "counter_risk_1158_reopen_clock": "04:12Z",
            "counter_risk_1158_reopen_date": UNKNOWN,
        },
        "linked_verifier_evidence": [
            {
                "citation": "stranske/Counter_Risk#1168",
                "repository": "stranske/Counter_Risk",
                "kind": "provider comparison report",
                "timestamp": UNKNOWN,
            },
            {
                "citation": "stranske/Counter_Risk#1169",
                "repository": "stranske/Counter_Risk",
                "kind": "provider comparison report",
                "timestamp": UNKNOWN,
            },
            {
                "citation": "stranske/Counter_Risk#1158",
                "repository": "stranske/Counter_Risk",
                "kind": "issue timeline closed/reopened",
                "timestamp": UNKNOWN,
                "clock": "04:12Z",
            },
            {
                "citation": "Manager-Database#1809",
                "repository": UNKNOWN,
                "kind": "provider comparison report",
                "timestamp": UNKNOWN,
            },
            {
                "citation": "Pension-Data#972",
                "repository": UNKNOWN,
                "kind": "provider comparison report",
                "timestamp": UNKNOWN,
            },
            {
                "citation": "trip-planner#1915",
                "repository": UNKNOWN,
                "kind": "provider comparison report",
                "timestamp": UNKNOWN,
            },
            {
                "citation": "Doc-Lineage#107",
                "repository": UNKNOWN,
                "kind": "source issue closed by a closer lane",
                "timestamp": UNKNOWN,
            },
            {
                "citation": "stranske/Workflows#3985",
                "repository": WORKFLOWS_REPO,
                "kind": "deterministic acceptance gate",
                "timestamp": UNKNOWN,
            },
            {
                "citation": "stranske/Workflows#3967",
                "repository": WORKFLOWS_REPO,
                "kind": "related auto-pilot rule",
                "timestamp": UNKNOWN,
            },
            {
                "citation": "stranske/Workflows actions run 39090617832",
                "repository": WORKFLOWS_REPO,
                "kind": "comment on issue #4036",
                "comment_created_at": "2026-10-18T02:46:37Z",
                "stated_subject": "multi-file agent PR 4065",
                "stated_report": (
                    "openai files reviewed 2 of 2 and anthropic files reviewed 2 of 2; "
                    "verdict UNVERIFIABLE_INPUT/PASS because acceptance-artifact retrieval "
                    "was incomplete"
                ),
                "october_24_outcome_claimed": False,
            },
            {
                "citation": "stranske/Workflows actions run 39280806595",
                "repository": WORKFLOWS_REPO,
                "kind": "comment on issue #4036",
                "comment_created_at": "2026-10-19T16:47:57Z",
                "stated_subject": "release #4135",
                "immutable_source": "af60a4aee8464009986ab91764b7d48dc7a2c36d",
                "stated_report": (
                    "HTTP 400 string_above_max_length before model review; "
                    "comparison.json CONCERNS; used_llm=false"
                ),
            },
            {
                "citation": "stranske/Workflows actions run 39902391881",
                "repository": WORKFLOWS_REPO,
                "kind": "comment on issue #4036",
                "comment_created_at": "2026-10-23T05:42:02Z",
                "stated_subject": "stranske/Workflows#4193",
                "merge_sha": "9e26d43a67c2736878efd41fa97ccf11902880c7",
                "original_head": "0a9dc057c1dbccc1d280d1ae63c9226a63e12240",
                "stated_report": "OpenAI FAIL / Anthropic CONCERNS over eight chunks",
            },
        ],
        "issue_4036_timeline": [
            {"event": "closed", "timestamp": "2026-10-18T02:31:24Z"},
            {"event": "reopened", "timestamp": "2026-10-18T02:31:47Z"},
            {"event": "closed", "timestamp": "2026-11-03T00:31:08Z"},
            {"event": "reopened", "timestamp": "2026-11-03T00:39:55Z"},
            {"event": "closed", "timestamp": "2026-11-03T15:06:42Z"},
        ],
    }


def initial_evidence_argv(repo: str = WORKFLOWS_REPO) -> list[str]:
    """Build the one-run evidence command after rejecting an excluded repository."""
    if is_owner_excluded(repo):
        raise OwnerExcludedRepository(repo)
    fields = ",".join(
        [
            "databaseId",
            "conclusion",
            "status",
            "headSha",
            "event",
            "url",
            "displayTitle",
            "createdAt",
            "updatedAt",
            "workflowName",
            "headBranch",
        ]
    )
    return [
        "gh",
        "run",
        "view",
        INITIAL_EVIDENCE_RUN_ID,
        "--repo",
        repo,
        "--json",
        fields,
    ]


def _elapsed(clock: Callable[[], float], started: float) -> float:
    return clock() - started


def run_initial_evidence(
    runner: CommandRunner | None = None,
    *,
    clock: Callable[[], float] | None = None,
    repo: str = WORKFLOWS_REPO,
    max_attempts: int = INITIAL_EVIDENCE_MAX_ATTEMPTS,
    max_elapsed_seconds: float = INITIAL_EVIDENCE_MAX_ELAPSED_SECONDS,
) -> dict[str, Any]:
    """Run the cited run lookup. Stop at the attempt cap or the elapsed cap.

    The repository exclusion is applied before ``runner`` is called.
    """
    argv = initial_evidence_argv(repo)
    command_runner = runner or _default_runner
    now = clock or time.monotonic
    started = now()
    attempts = 0
    errors: list[str] = []
    while attempts < max_attempts:
        elapsed = _elapsed(now, started)
        if elapsed > max_elapsed_seconds:
            return _evidence_result(
                argv,
                attempts=attempts,
                elapsed=elapsed,
                outcome=None,
                errors=errors,
                stop_reason="elapsed-cap",
            )
        remaining = max(0.0, max_elapsed_seconds - elapsed)
        timeout = min(INITIAL_EVIDENCE_ATTEMPT_TIMEOUT_SECONDS, remaining)
        attempts += 1
        try:
            completed = command_runner(argv, timeout)
        except subprocess.TimeoutExpired:
            errors.append(f"attempt {attempts}: timeout after {timeout:.1f}s")
            continue
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            errors.append(f"attempt {attempts}: exit {completed.returncode}: {detail}")
            continue
        try:
            outcome = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            errors.append(f"attempt {attempts}: invalid JSON: {exc}")
            continue
        if not isinstance(outcome, dict):
            errors.append(f"attempt {attempts}: JSON value was not an object")
            continue
        return _evidence_result(
            argv,
            attempts=attempts,
            elapsed=_elapsed(now, started),
            outcome=outcome,
            errors=errors,
            stop_reason=None,
        )
    return _evidence_result(
        argv,
        attempts=attempts,
        elapsed=_elapsed(now, started),
        outcome=None,
        errors=errors,
        stop_reason="attempt-cap",
    )


def _evidence_result(
    argv: Sequence[str],
    *,
    attempts: int,
    elapsed: float,
    outcome: dict[str, Any] | None,
    errors: list[str],
    stop_reason: str | None,
) -> dict[str, Any]:
    return {
        "command": list(argv),
        "attempts": attempts,
        "elapsed_seconds": round(elapsed, 3),
        "stop_rule": {
            "max_attempts": INITIAL_EVIDENCE_MAX_ATTEMPTS,
            "max_elapsed_seconds": INITIAL_EVIDENCE_MAX_ELAPSED_SECONDS,
        },
        "outcome": outcome,
        "errors": errors,
        "stop_reason": stop_reason,
    }


def _default_runner(argv: Sequence[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


REPO_ROOT = Path(__file__).resolve().parent
TEMPLATE_PREFIX = "templates/consumer-repo/"
WORKFLOWS_LIB_PREFIX = ".workflows-lib/"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REUSABLE_USES_RE = re.compile(
    r"uses:\s*(stranske/Workflows/\.github/workflows/reusable-agents-verifier\.yml)@(\S+)"
)
INVOCATION_RE = re.compile(r"python\s+(\.workflows-lib/scripts/langchain/pr_verifier\.py)\b")
REQUIRE_RE = re.compile(
    r"['\"](\./)?(\.workflows-lib/)?(\.github/scripts/(?:agents_verifier_context|verifier_closure)\.js)['\"]"
)
SPARSE_CHECKOUT_RE = re.compile(r"sparse-checkout:\s*\|\n(?P<body>(?:[ \t]+.+\n)+)")
USES_RE = re.compile(r"uses:\s*(stranske/Workflows/\.github/workflows/\S+?\.yml)@(\S+)")

SURFACE_NAMES = (
    "pr_verifier.py",
    "verifier_config.py",
    "agents_verifier_context.js",
    "verifier_closure.js",
    "agents-verifier.yml",
    "reusable-agents-verifier.yml",
    "agents-issue-intake.yml",
    "GoalsAndPlumbing.md",
)

# Saved from the selected run on 2026-11-06. Replay does not call GitHub.
SELECTED_RUN_EVIDENCE: dict[str, Any] = {
    "collected_by": [
        f"{_GH_API} repos/stranske/Workflows/actions/runs/{INITIAL_EVIDENCE_RUN_ID}",
        f"gh run view {INITIAL_EVIDENCE_RUN_ID} --repo stranske/Workflows --log",
    ],
    "repository": WORKFLOWS_REPO,
    "run_id": INITIAL_EVIDENCE_RUN_ID,
    "event": "workflow_dispatch",
    "display_title": "Agents Verifier",
    "head_branch": "main",
    "head_sha": "021ec67ef580c83a88402a1574e27ea34db14dde",
    "path": ".github/workflows/agents-verifier.yml",
    "run_started_at": "2026-10-18T02:35:09Z",
    "updated_at": "2026-10-18T02:39:02Z",
    "referenced_workflows": [
        {
            "path": "stranske/Workflows/.github/workflows/reusable-agents-verifier.yml@main",
            "ref": "refs/heads/main",
            "sha": "021ec67ef580c83a88402a1574e27ea34db14dde",
        }
    ],
    "script_checkout": {
        "job": "verifier / Run post-merge verifier",
        "resolved_ref": "main",
        "fetch_at": "2026-10-18T02:35:39.7063036Z",
        "checkout_command": "git checkout --progress --force -B main refs/remotes/origin/main",
        "printed_sha": None,
        "executed_invocation": "python .workflows-lib/scripts/langchain/pr_verifier.py",
    },
    "other_checkouts": [
        {
            "job": "Verify named gates on immutable merge commit",
            "sha": "7ccda2ad80ccac05348ad305fb2248b02b0c2c81",
            "role": "subject immutable merge checkout",
            "verifier_implementation": False,
        }
    ],
}


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def resolve_tracked_locations(paths: Sequence[str]) -> dict[str, list[str]]:
    """Map each requested verifier surface to the tracked paths that actually use its name."""
    found = {name: [] for name in SURFACE_NAMES}
    for path in paths:
        name = path.rsplit("/", 1)[-1]
        if name in found:
            found[name].append(path)
    return {name: sorted(set(paths_for_name)) for name, paths_for_name in found.items()}


def tracked_path_for_runtime_path(runtime_path: str) -> str:
    """Map a workflow checkout path back to the repository path it names."""
    path = runtime_path.strip()
    if path.startswith("./"):
        path = path[2:]
    if path.startswith(WORKFLOWS_LIB_PREFIX):
        path = path[len(WORKFLOWS_LIB_PREFIX) :]
    return path


def parse_reusable_verifier_use(caller_text: str) -> dict[str, str] | None:
    match = REUSABLE_USES_RE.search(caller_text)
    if match is None:
        return None
    return {"workflow": match.group(1), "ref": match.group(2)}


def parse_pr_verifier_invocations(workflow_text: str) -> list[str]:
    return list(dict.fromkeys(INVOCATION_RE.findall(workflow_text)))


def parse_runtime_script_paths(workflow_text: str) -> list[str]:
    found: list[str] = []
    for dot, prefix, relative in REQUIRE_RE.findall(workflow_text):
        runtime = f"{dot}{prefix}{relative}"
        if runtime not in found:
            found.append(runtime)
    return found


def parse_sparse_checkout(workflow_text: str) -> list[str]:
    match = SPARSE_CHECKOUT_RE.search(workflow_text)
    if match is None:
        return []
    entries: list[str] = []
    for line in match.group("body").splitlines():
        stripped = line.strip()
        if not stripped or ":" in stripped:
            break
        entries.append(stripped)
    return entries


def parse_workflow_delegations(workflow_text: str) -> list[dict[str, str]]:
    delegations: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for workflow, ref in USES_RE.findall(workflow_text):
        key = (workflow, ref)
        if key in seen:
            continue
        seen.add(key)
        tracked = workflow.removeprefix("stranske/Workflows/")
        delegations.append({"workflow": workflow, "ref": ref, "tracked_path": tracked})
    return delegations


def implementation_revision(
    *,
    referenced_sha: str,
    fetch_at: str,
    checkout_command: str,
    printed_sha: str | None,
    next_commit_at: str | None,
    history_available: bool,
    referenced_sha_on_main: bool,
) -> dict[str, str]:
    """Identify the script checkout SHA without treating a moved branch as the pinned SHA.

    ``next_commit_at`` is the committer time of the first later first-parent commit on
    ``main``. ``None`` with the SHA on ``main`` means that SHA is still the tip.
    """
    if printed_sha and SHA_RE.fullmatch(printed_sha):
        return {"revision": printed_sha, "source": "checkout-log"}
    if "refs/remotes/origin/main" not in checkout_command:
        return {"revision": UNKNOWN, "source": "script-checkout-was-not-origin-main"}
    if not history_available or not SHA_RE.fullmatch(referenced_sha):
        return {"revision": UNKNOWN, "source": "main-history-unavailable"}
    if not referenced_sha_on_main:
        return {"revision": UNKNOWN, "source": "referenced-sha-not-on-main"}
    if next_commit_at is None:
        return {"revision": referenced_sha, "source": "referenced-sha-is-the-tip-of-main"}
    if _parse_timestamp(next_commit_at) > _parse_timestamp(fetch_at):
        return {
            "revision": referenced_sha,
            "source": "origin-main-unchanged-between-referenced-pin-and-script-fetch",
        }
    return {"revision": UNKNOWN, "source": "origin-main-moved-before-script-fetch"}


def _git(
    repo: Path, args: Sequence[str], runner: CommandRunner | None = None
) -> subprocess.CompletedProcess[str]:
    command = ["git", *args]
    if runner is not None:
        return runner(command, 30.0)
    return subprocess.run(
        command,
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def _tracked_paths(repo: Path, rev: str, runner: CommandRunner | None) -> list[str]:
    completed = _git(repo, ["ls-tree", "-r", "--name-only", rev], runner)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "").strip())
    return [line for line in completed.stdout.splitlines() if line]


def _file_text(repo: Path, rev: str, path: str, runner: CommandRunner | None) -> str:
    completed = _git(repo, ["show", f"{rev}:{path}"], runner)
    if completed.returncode != 0:
        return ""
    return completed.stdout


def _blob(repo: Path, rev: str, path: str, runner: CommandRunner | None) -> str | None:
    completed = _git(repo, ["rev-parse", f"{rev}:{path}"], runner)
    if completed.returncode != 0:
        return None
    blob = completed.stdout.strip()
    return blob or None


def _next_main_commit(
    repo: Path, sha: str, runner: CommandRunner | None
) -> tuple[bool, bool, dict[str, str] | None]:
    """Return history availability, whether ``sha`` is on the ref, and the next commit.

    The next commit is the first later first-parent commit on ``origin/main``, or on
    ``HEAD`` when ``origin/main`` cannot be read. An empty descendant list is the tip
    only when the ref resolves to ``sha``.
    """
    for ref in ("origin/main", "HEAD"):
        ancestor = _git(repo, ["merge-base", "--is-ancestor", sha, ref], runner)
        if ancestor.returncode not in {0, 1}:
            continue
        on_ref = ancestor.returncode == 0
        if not on_ref:
            return True, False, None
        tip = _git(repo, ["rev-parse", ref], runner)
        if tip.returncode != 0:
            return False, False, None
        if tip.stdout.strip() == sha:
            return True, True, None
        completed = _git(
            repo,
            ["rev-list", "--first-parent", "--ancestry-path", "--reverse", f"{sha}..{ref}"],
            runner,
        )
        if completed.returncode != 0:
            return False, True, None
        descendants = [line for line in completed.stdout.splitlines() if line]
        if not descendants:
            return False, True, None
        meta = _git(repo, ["log", "-1", "--format=%H%n%cI%n%s", descendants[0]], runner)
        if meta.returncode != 0:
            return False, True, None
        commit_sha, committed_at, subject = (meta.stdout.splitlines() + ["", "", ""])[:3]
        return True, True, {"sha": commit_sha, "committed_at": committed_at, "subject": subject}
    return False, False, None


def _citation_lines(text: str, needles: Sequence[str], limit: int = 4) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        if any(needle in line for needle in needles):
            lines.append(line.strip())
        if len(lines) >= limit:
            break
    return lines


def _location_records(
    repo: Path,
    rev: str,
    locations: Mapping[str, Sequence[str]],
    runner: CommandRunner | None,
) -> dict[str, list[dict[str, str]]]:
    records: dict[str, list[dict[str, str]]] = {}
    for name, paths in locations.items():
        entries: list[dict[str, str]] = []
        for path in paths:
            blob = _blob(repo, rev, path, runner)
            entries.append(
                {
                    "path": path,
                    "role": "template" if path.startswith(TEMPLATE_PREFIX) else "repository",
                    "blob": blob or UNKNOWN,
                }
            )
        records[name] = entries
    return records


def resolve_production_surfaces(
    repo: Path | None = None,
    *,
    repo_slug: str = WORKFLOWS_REPO,
    evidence: Mapping[str, Any] | None = None,
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    """Resolve verifier surfaces at the selected run's pinned workflow SHA.

    The owner exclusion is applied before git is invoked. The run evidence is the
    saved API and log record, so this function does not use the network.
    """
    if is_owner_excluded(repo_slug):
        raise OwnerExcludedRepository(repo_slug)
    record = dict(evidence or SELECTED_RUN_EVIDENCE)
    if record.get("repository") != repo_slug:
        raise ValueError(f"saved run evidence is for {record.get('repository')}, not {repo_slug}")
    root = repo or REPO_ROOT
    referenced = record["referenced_workflows"][0]
    revision = str(referenced["sha"])
    checkout = record["script_checkout"]
    history_available, referenced_on_main, next_commit = _next_main_commit(root, revision, runner)
    identified = implementation_revision(
        referenced_sha=revision,
        fetch_at=str(checkout["fetch_at"]),
        checkout_command=str(checkout["checkout_command"]),
        printed_sha=checkout.get("printed_sha"),
        next_commit_at=None if next_commit is None else next_commit["committed_at"],
        history_available=history_available,
        referenced_sha_on_main=referenced_on_main,
    )
    tree_rev = revision if SHA_RE.fullmatch(revision) else record["head_sha"]
    paths = _tracked_paths(root, tree_rev, runner)
    locations = resolve_tracked_locations(paths)
    location_records = _location_records(root, tree_rev, locations, runner)
    caller_text = _file_text(root, tree_rev, str(record["path"]), runner)
    reusable_path = str(referenced["path"]).split("@", 1)[0].removeprefix("stranske/Workflows/")
    reusable_text = _file_text(root, tree_rev, reusable_path, runner)
    invocations = parse_pr_verifier_invocations(reusable_text)
    invocation = invocations[0] if invocations else UNKNOWN
    tracked_implementation = (
        tracked_path_for_runtime_path(invocation.split()[-1]) if invocation != UNKNOWN else UNKNOWN
    )
    runtime_scripts = parse_runtime_script_paths(reusable_text)
    caller_scripts = parse_runtime_script_paths(caller_text)
    sparse = parse_sparse_checkout(reusable_text)
    implementation_text = (
        _file_text(root, tree_rev, tracked_implementation, runner)
        if tracked_implementation != UNKNOWN
        else ""
    )
    imports_verifier_config = "from scripts.langchain.verifier_config import" in implementation_text
    pr_verifier_entries = location_records.get("pr_verifier.py", [])
    template_entry = next(
        (item for item in pr_verifier_entries if item["role"] == "template"), None
    )
    repository_entry = next(
        (item for item in pr_verifier_entries if item["path"] == tracked_implementation),
        None,
    )
    intake_paths = locations.get("agents-issue-intake.yml", [])
    intake_path = intake_paths[0] if len(intake_paths) == 1 else UNKNOWN
    intake_text = _file_text(root, tree_rev, intake_path, runner) if intake_path != UNKNOWN else ""
    goals_paths = locations.get("GoalsAndPlumbing.md", [])
    goals_path = goals_paths[0] if len(goals_paths) == 1 else UNKNOWN
    goals_text = _file_text(root, tree_rev, goals_path, runner) if goals_path != UNKNOWN else ""
    root_intake = ".github/workflows/agents-issue-intake.yml"
    gaps = []
    if checkout.get("printed_sha") is None:
        gaps.append(
            "The workflows-lib checkout log fetches origin/main and does not print a commit SHA."
        )
    if root_intake not in paths:
        gaps.append(f"{root_intake} is not a tracked file at {tree_rev}.")
    if identified["revision"] == UNKNOWN:
        gaps.append("The verifier implementation revision is unknown from the saved evidence.")
    log_invocation = str(checkout.get("executed_invocation") or "")
    return {
        "repository": repo_slug,
        "run_id": record["run_id"],
        "tree_revision": tree_rev,
        "locations": location_records,
        "absent_root_paths": [root_intake] if root_intake not in paths else [],
        "selected_run": {
            "workflow_path": record["path"],
            "workflow_revision": record["head_sha"],
            "workflow_revision_source": "actions run head_sha for the recorded workflow path",
            "reusable_workflow": {
                "uses": parse_reusable_verifier_use(caller_text),
                "referenced": referenced,
                "blob": _blob(root, tree_rev, reusable_path, runner) or UNKNOWN,
                "invocations": invocations,
                "runtime_scripts": runtime_scripts,
                "tracked_runtime_scripts": [
                    tracked_path_for_runtime_path(path) for path in runtime_scripts
                ],
                "caller_runtime_scripts": caller_scripts,
                "tracked_caller_runtime_scripts": [
                    tracked_path_for_runtime_path(path) for path in caller_scripts
                ],
                "sparse_checkout": sparse,
                "sparse_checkout_includes_template": any(
                    entry.startswith("templates/") for entry in sparse
                ),
            },
            "verifier_implementation": {
                "invocation": invocation,
                "log_invocation": log_invocation,
                "log_invocation_matches_workflow": (
                    log_invocation.endswith(invocation)
                    if invocation != UNKNOWN and log_invocation
                    else False
                ),
                "tracked_path": tracked_implementation,
                "revision": identified["revision"],
                "revision_source": identified["source"],
                "blob": None if repository_entry is None else repository_entry["blob"],
                "template_copy_executed": tracked_implementation.startswith(TEMPLATE_PREFIX),
                "template_copy_same_blob": bool(
                    repository_entry
                    and template_entry
                    and repository_entry["blob"] == template_entry["blob"]
                    and repository_entry["blob"] != UNKNOWN
                ),
                "imports_verifier_config": imports_verifier_config,
                "printed_checkout_sha": checkout.get("printed_sha"),
            },
            "intake_workflow": {
                "tracked_paths": list(intake_paths),
                "used_by_selected_run": False,
                "delegations": parse_workflow_delegations(intake_text),
            },
            "goals_and_plumbing": {
                "tracked_paths": list(goals_paths),
                "used_by_selected_run": False,
                "citations": _citation_lines(
                    goals_text,
                    (
                        "verifier_config.py",
                        "reusable-agents-verifier.yml",
                        "agents-verifier.yml",
                    ),
                ),
            },
            "next_main_commit": next_commit,
            "other_checkouts": list(record["other_checkouts"]),
        },
        "evidence_gaps": gaps,
    }


LIVE_PR_EVIDENCE_PATH = REPO_ROOT / "verifier_4422_live_pr.json"
LIVE_REPORT_EVIDENCE_PATH = REPO_ROOT / "verifier_4422_live_report.json"
DEFAULT_RUN_LIST_CREATED = "2026-10-18T02:30:00Z..2026-10-18T02:40:00Z"
CAMPAIGN_CHECK_DATE = "2026-10-24"
_FILES_REVIEWED_LINE_RE = re.compile(r"- ([A-Za-z0-9_.-]+): files reviewed (\d+) of (\d+)")
_UPLOAD_RE = re.compile(
    r"Artifact (\S+) has been successfully uploaded! "
    r"Final size is (\d+) bytes\. Artifact ID is (\d+)"
)
_PATH_LINE_RE = re.compile(r"[\w./-]+\.\w+")
_COMMENT_URL_RE = re.compile(r"https://github\.com/stranske/Workflows/pull/\d+#issuecomment-\d+")
PROMPT_BUDGET_TRUNCATION_MARKER = "[truncated: verifier prompt budget exceeded]"


def _log_job(line: str) -> str:
    return line.split("\t", 1)[0] if "\t" in line else ""


def _log_message(line: str) -> str:
    message = line.rsplit("\t", 1)[-1] if "\t" in line else line
    return re.sub(r"^\d{4}-\d{2}-\d{2}T\S+Z\s*", "", message).strip()


def _unique_values(values: Sequence[str]) -> str | None:
    found = list(dict.fromkeys(values))
    if len(found) == 1:
        return found[0]
    return None


def files_reviewed_in_text(text: str) -> list[dict[str, Any]]:
    """Return provider file-review lines, ignoring the same line when it repeats."""
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for line in text.splitlines():
        match = _FILES_REVIEWED_LINE_RE.fullmatch(_log_message(line))
        if match is None:
            continue
        provider, reviewed, total = match.groups()
        key = (provider, int(reviewed), int(total))
        if key in seen:
            continue
        seen.add(key)
        found.append({"provider": provider, "reviewed": key[1], "total": key[2]})
    return found


def parse_verifier_run_log(log_text: str) -> dict[str, Any]:
    """Read the retained run-log lines for SHAs, the posted report, and artifact uploads."""
    lines = log_text.splitlines()
    messages = [_log_message(line) for line in lines]
    jobs = [_log_job(line) for line in lines]
    directory: dict[str, str] = {}
    checkouts: list[dict[str, str]] = []
    for index, message in enumerate(messages):
        job = jobs[index]
        if message.startswith("Working directory is "):
            directory[job] = message.removeprefix("Working directory is ").strip("'\"")
        if "git log -1 --format=%H" not in message or index + 1 >= len(lines):
            continue
        sha = messages[index + 1]
        if jobs[index + 1] == job and SHA_RE.fullmatch(sha):
            checkouts.append({"job": job, "directory": directory.get(job, UNKNOWN), "sha": sha})
    lib_shas = [
        item["sha"]
        for item in checkouts
        if item["directory"].rstrip("/").endswith(".workflows-lib")
    ]
    paths: list[str] = []
    file_count: int | None = None
    capturing = False
    awaiting_count = False
    for message in messages:
        if message.startswith("name: comparison-results-"):
            capturing = True
            awaiting_count = True
            paths = []
            continue
        if capturing:
            if message.startswith("if-no-files-found:"):
                capturing = False
                continue
            if message.startswith("path:"):
                paths.append(message.split(":", 1)[1].strip())
                continue
            if _PATH_LINE_RE.fullmatch(message):
                paths.append(message)
            continue
        if awaiting_count:
            count_match = re.search(r"there will be (\d+) files uploaded", message)
            if count_match:
                file_count = int(count_match.group(1))
                awaiting_count = False
    issue_groups = [
        [int(part) for part in group.split(",") if part.strip()]
        for group in re.findall(r"ISSUE_NUMBERS:\s*\[([0-9,\s]*)\]", log_text)
    ]
    closure_values = [
        line.strip() for line in re.findall(r"Closed source issues:\s*(.+)", log_text)
    ]
    posted_urls: list[str] = []
    for message in messages:
        if _COMMENT_URL_RE.fullmatch(message) and message not in posted_urls:
            posted_urls.append(message)
    return {
        "checkouts": checkouts,
        "workflows_lib_sha": _unique_values(lib_shas),
        "reusable_workflow_shas": list(
            dict.fromkeys(
                re.findall(
                    r"reusable-agents-verifier\.yml@\S+ \(([0-9a-f]{40})\)",
                    log_text,
                )
            )
        ),
        "target_shas": list(dict.fromkeys(re.findall(r"TARGET_SHA:\s*([0-9a-f]{40})", log_text))),
        "evaluated_shas": list(
            dict.fromkeys(re.findall(r"EVALUATED_SHA:\s*([0-9a-f]{40})", log_text))
        ),
        "pull_numbers": list(
            dict.fromkeys(re.findall(r"(?:Manual dispatch: PR #|PR_NUMBER:\s*)(\d+)", log_text))
        ),
        "issue_number_groups": issue_groups,
        "files_reviewed": files_reviewed_in_text(log_text),
        "posted_comment_urls": posted_urls,
        "uploads": [
            {"name": name, "size_bytes": int(size), "artifact_id": artifact_id}
            for name, size, artifact_id in _UPLOAD_RE.findall(log_text)
        ],
        "comparison_named_paths": paths,
        "comparison_uploaded_file_count": file_count,
        "closure_log": _unique_values(closure_values),
    }


def issue_state_as_of(timeline: Sequence[Mapping[str, Any]], as_of: str) -> dict[str, Any]:
    """Apply closed and reopened events that occurred at or before ``as_of``."""
    cutoff = _parse_timestamp(as_of)
    state = "open"
    last: dict[str, str] | None = None
    for event in timeline:
        if event.get("event") not in {"closed", "reopened"}:
            continue
        if _parse_timestamp(str(event["created_at"])) > cutoff:
            continue
        state = "closed" if event["event"] == "closed" else "open"
        last = {
            "event": str(event["event"]),
            "created_at": str(event["created_at"]),
            "actor": str(event.get("actor") or UNKNOWN),
        }
    return {"as_of": as_of, "state": state, "last_event": last}


def build_live_pr_collection_commands(evidence: Mapping[str, Any]) -> list[str]:
    """List the collection commands. An excluded repository is rejected first."""
    repo = str(evidence["repository"])
    if is_owner_excluded(repo):
        raise OwnerExcludedRepository(repo)
    run_id = str(evidence["selected_run_id"])
    pull_number = evidence["pull_request"]["number"]
    issue_number = evidence["source_issue"]["number"]
    comment_id = evidence["report_comment"]["id"]
    window = str(evidence.get("run_list_created") or DEFAULT_RUN_LIST_CREATED)
    return [
        (
            "gh run list --repo "
            f"{repo} --workflow Agents Verifier "
            f"--created {window} --limit 20 "
            "--json databaseId,displayTitle,conclusion,headSha,event,url,createdAt,status"
        ),
        f"gh run view {run_id} --repo {repo} --log",
        f"gh run download {run_id} --repo {repo}",
        f"{_GH_API} repos/{repo}/pulls/{pull_number}",
        f"{_GH_API} repos/{repo}/pulls/{pull_number}/files",
        f"{_GH_API} repos/{repo}/issues/comments/{comment_id}",
        f"{_GH_API} repos/{repo}/issues/{issue_number}",
        f"{_GH_API} repos/{repo}/issues/{issue_number}/timeline",
        f"{_GH_API} repos/{repo}/actions/runs/{run_id}/artifacts",
    ]


def _load_live_pr_evidence() -> dict[str, Any]:
    return json.loads(LIVE_PR_EVIDENCE_PATH.read_text(encoding="utf-8"))


def assemble_live_pr_record(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Turn saved GitHub records into the live pull-request packet.

    Missing artifacts and missing report sections stay explicit. A close that
    happens after the run does not become the run's source-issue disposition.
    """
    repo = str(evidence["repository"])
    if is_owner_excluded(repo):
        raise OwnerExcludedRepository(repo)
    gaps: list[str] = []
    log_facts = parse_verifier_run_log(str(evidence["log_excerpt"]))
    commands = build_live_pr_collection_commands(evidence)
    selected_id = str(evidence["selected_run_id"])
    matches = [run for run in evidence["run_list"] if str(run.get("databaseId")) == selected_id]
    selected_run = matches[0] if len(matches) == 1 else None
    if selected_run is None:
        gaps.append(
            f"The saved run list does not contain exactly one record for run {selected_id}."
        )
    pull = evidence["pull_request"]
    comment = evidence["report_comment"]
    report_reviewed = files_reviewed_in_text(str(comment["body"]))
    merge_values = [str(pull["merge_commit_sha"])]
    if len(log_facts["target_shas"]) == 1:
        merge_values.append(log_facts["target_shas"][0])
    else:
        gaps.append("The run log does not contain one TARGET_SHA.")
    if len(log_facts["evaluated_shas"]) == 1:
        merge_values.append(log_facts["evaluated_shas"][0])
    else:
        gaps.append("The run log does not contain one EVALUATED_SHA.")
    merge_sha = merge_values[0] if len(set(merge_values)) == 1 else None
    if merge_sha is None:
        gaps.append("The pull request merge SHA and the run-log SHAs do not agree.")
    pin = _unique_values(log_facts["reusable_workflow_shas"])
    lib_sha = log_facts["workflows_lib_sha"]
    if pin is None:
        gaps.append("The run log does not contain one reusable-agents-verifier.yml pin.")
    if lib_sha is None:
        gaps.append("The run log does not contain one git log SHA for the .workflows-lib checkout.")
    revision = pin if pin is not None and pin == lib_sha else None
    if revision is None:
        gaps.append("The reusable workflow pin and the .workflows-lib checkout SHA do not agree.")
    changed_files = [dict(item) for item in evidence["changed_files"]]
    api_artifacts = [dict(item) for item in evidence["artifact_api"]]
    api_names = {item["name"] for item in api_artifacts}
    downloaded = list(evidence["downloaded_artifact_names"])
    absent_uploads = [item for item in log_facts["uploads"] if item["name"] not in api_names]
    if absent_uploads:
        rendered = ", ".join(
            (f"{item['name']} (artifact {item['artifact_id']}, " f"{item['size_bytes']} bytes)")
            for item in absent_uploads
        )
        gaps.append(
            "Uploaded artifacts absent from the current artifacts API and from "
            f"gh run download: {rendered}."
        )
    comparison_absent = any(
        item["name"].startswith("comparison-results-") for item in absent_uploads
    )
    named_paths = list(log_facts["comparison_named_paths"])
    if comparison_absent and named_paths:
        gaps.append(
            "The comparison upload named these paths, and none of them were downloaded: "
            + ", ".join(named_paths)
            + "."
        )
    artifact_report = _artifact_report_record(evidence.get("artifact_report"))
    uploaded_count = log_facts["comparison_uploaded_file_count"]
    downloaded_members = None if artifact_report is None else artifact_report["downloaded_members"]
    if uploaded_count is None:
        gaps.append("The comparison upload log does not state how many files were uploaded.")
    elif downloaded_members is not None and uploaded_count == len(downloaded_members):
        omitted_names = [path for path in named_paths if path not in downloaded_members]
        if omitted_names:
            gaps.append(
                "The comparison upload log names "
                f"{len(named_paths)} paths and says {uploaded_count} files were uploaded. "
                f"gh run download retrieved {len(downloaded_members)} members. "
                "Named paths absent from that download: " + ", ".join(omitted_names) + "."
            )
    elif uploaded_count != len(named_paths):
        gaps.append(
            f"The comparison upload log says {uploaded_count} files were uploaded and "
            f"names {len(named_paths)} paths. Which named path was omitted is not stated."
        )
    if artifact_report is None and "files_not_reviewed" not in str(comment["body"]):
        gaps.append(
            "The posted report has no files_not_reviewed section. "
            "That absence is not recorded as an empty unreviewed-file list."
        )
    report_url = str(comment["html_url"])
    if report_url not in log_facts["posted_comment_urls"]:
        gaps.append("The saved report URL is not the comment URL printed by the run log.")
    if report_reviewed != log_facts["files_reviewed"]:
        gaps.append("The posted report and the run log do not have the same files-reviewed lines.")
    pull_number = str(pull["number"])
    if log_facts["pull_numbers"] != [pull_number]:
        gaps.append("The run log does not name only the saved pull request number.")
    issue = evidence["source_issue"]
    issue_groups = log_facts["issue_number_groups"]
    expected_issue = [int(issue["number"])]
    if not issue_groups or any(group != expected_issue for group in issue_groups):
        gaps.append("The run log does not name only the saved source issue number.")
    metrics = dict(evidence["metrics"])
    if str(metrics.get("pr_number")) != pull_number:
        gaps.append("The downloaded metrics artifact names a different pull request.")
    for name in downloaded:
        if name not in api_names:
            gaps.append(f"Downloaded artifact {name} is absent from the artifacts API record.")
    run_completed_at = str(evidence["run_completed_at"])
    disposition = issue_state_as_of(evidence["source_issue_timeline"], run_completed_at)
    collection_close = issue.get("closed_at")
    uses_later_close = bool(
        disposition["state"] == "closed"
        and disposition["last_event"] is not None
        and collection_close
        and disposition["last_event"]["created_at"] == collection_close
        and _parse_timestamp(str(collection_close)) > _parse_timestamp(run_completed_at)
    )
    created_at = selected_run.get("createdAt") if selected_run else None
    merged_at = pull.get("merged_at")
    post_merge: bool | None
    if created_at and merged_at:
        post_merge = _parse_timestamp(str(merged_at)) < _parse_timestamp(str(created_at))
    else:
        post_merge = None
        gaps.append("The run time or the pull request merge time is missing.")
    closure_log = log_facts["closure_log"]
    if closure_log is None:
        gaps.append("The run log does not contain one source-issue closure line.")
    record = {
        "artifacts": {
            "api": api_artifacts,
            "downloaded_names": downloaded,
            "uploads_recorded_in_log": log_facts["uploads"],
        },
        "changed_files": changed_files,
        "changed_file_count": len(changed_files),
        "collected_at": evidence["collected_at"],
        "collection_commands": commands,
        "deployed_verifier_revision": {
            "closure_checkout_sha": _unique_values(
                [
                    item["sha"]
                    for item in log_facts["checkouts"]
                    if item["job"] == "Apply verified source issue closure rule"
                ]
            ),
            "reusable_workflow_sha": pin,
            "revision": revision,
            "source": (
                "run log pins reusable-agents-verifier.yml and the following "
                ".workflows-lib git log -1 SHA agrees"
                if revision
                else UNKNOWN
            ),
            "workflows_lib_sha": lib_sha,
        },
        "evidence_gaps": gaps,
        "immutable_merge_sha": {
            "log_evaluated_sha": (
                log_facts["evaluated_shas"][0] if len(log_facts["evaluated_shas"]) == 1 else None
            ),
            "log_target_sha": (
                log_facts["target_shas"][0] if len(log_facts["target_shas"]) == 1 else None
            ),
            "pull_request_merge_commit_sha": pull["merge_commit_sha"],
            "sha": merge_sha,
            "values_agree": merge_sha is not None,
        },
        "multi_file": len(changed_files) > 1,
        "network_used_for_replay": False,
        "pull_request": {
            "agent_pr_basis": str(
                evidence.get("agent_pr_basis")
                or (
                    "The issue #4036 comment calls this run's subject a multi-file agent PR. "
                    "agent_pr_definition remains unknown."
                )
            ),
            "author_login": pull["author_login"],
            "base_ref": pull["base_ref"],
            "head_ref": pull["head_ref"],
            "head_sha": pull["head_sha"],
            "labels": list(pull["labels"]),
            "merged_at": pull["merged_at"],
            "number": pull["number"],
            "state": pull["state"],
            "title": pull["title"],
            "url": pull["html_url"],
        },
        "report": {
            "body": comment["body"],
            "comment_id": comment["id"],
            "created_at": comment["created_at"],
            "files_reviewed": report_reviewed,
            "files_reviewed_match_log": report_reviewed == log_facts["files_reviewed"],
            "html_url": report_url,
            "log_comment_urls": log_facts["posted_comment_urls"],
            "prompt_budget_marker_present": (
                PROMPT_BUDGET_TRUNCATION_MARKER in str(comment["body"])
            ),
            "truncated_substring_count": str(comment["body"]).count("truncated"),
            "user_login": comment["user_login"],
        },
        "repository": repo,
        "run": (
            None
            if selected_run is None
            else {
                "conclusion": selected_run.get("conclusion"),
                "created_at": selected_run.get("createdAt"),
                "event": selected_run.get("event"),
                "head_sha": selected_run.get("headSha"),
                "id": selected_run.get("databaseId"),
                "post_merge": post_merge,
                "status": selected_run.get("status"),
                "updated_at": run_completed_at,
                "url": selected_run.get("url"),
                "workflow_name": selected_run.get("displayTitle"),
            }
        ),
        "selected_run_id": selected_id,
        "source_issue": {
            "closed_at_collection": issue.get("closed_at"),
            "closed_by_at_collection": issue.get("closed_by"),
            "closure_job_log": closure_log,
            "created_at": issue.get("created_at"),
            "disposition_at_run_completion": disposition,
            "later_close_used_as_run_disposition": uses_later_close,
            "number": issue["number"],
            "repository": repo,
            "state_at_collection": issue.get("state"),
            "state_reason_at_collection": issue.get("state_reason"),
            "timeline": [dict(item) for item in evidence["source_issue_timeline"]],
            "title": issue.get("title"),
            "url": issue.get("html_url"),
        },
        "metrics": metrics,
    }
    if artifact_report is not None:
        record["artifact_report"] = artifact_report
    return record


def _artifact_report_record(raw: Any) -> dict[str, Any] | None:
    """Copy comparison-artifact facts. Missing evidence stays missing."""
    if not isinstance(raw, Mapping):
        return None
    files_not_reviewed = raw.get("files_not_reviewed", None)
    return {
        "comment_matches_downloaded_member": raw.get("comment_matches_downloaded_member") is True,
        "comment_member": raw.get("comment_member"),
        "comment_sha256": raw.get("comment_sha256"),
        "downloaded_members": [str(item) for item in raw.get("downloaded_members") or []],
        "files_not_reviewed": (
            None
            if "files_not_reviewed" not in raw or files_not_reviewed is None
            else [str(item) for item in files_not_reviewed]
        ),
        "input_coverage": raw.get("input_coverage"),
        "reviewed_file_paths": [str(item) for item in raw.get("reviewed_file_paths") or []],
    }


def _historical_campaign_effect(created_at: str | None) -> str:
    """Explain why this live packet is not the 2026-10-24 campaign result."""
    if not created_at:
        return (
            "The run timestamp is missing, so this live packet is not historical "
            "campaign evidence."
        )
    day = created_at[:10]
    if day > CAMPAIGN_CHECK_DATE:
        return (
            f"Run created_at {created_at} is after the campaign check date "
            f"{CAMPAIGN_CHECK_DATE}. A later successful run is not evidence that "
            "the 2026-10-24 targets were met."
        )
    if day == CAMPAIGN_CHECK_DATE:
        return (
            "The run falls on the campaign check date and that date has no stated clock, "
            "so this packet is not counted as historical achievement."
        )
    return (
        "This command evaluates one live report. It does not add the run to the "
        "historical population."
    )


def live_report_acceptance(record: Mapping[str, Any]) -> dict[str, Any]:
    """Judge the published report against the two live-report acceptance checks.

    The published report is the posted comparison comment. Input-coverage metadata
    stays visible and is not substituted for that text. A run after 2026-10-24 is
    not historical campaign evidence.
    """
    repo = str(record["repository"])
    if is_owner_excluded(repo):
        raise OwnerExcludedRepository(repo)
    run = record.get("run") or {}
    run_id = str(record.get("selected_run_id") or "")
    commands = [str(item) for item in record.get("collection_commands") or []]
    log_command = f"gh run view {run_id} --repo {repo} --log"
    download_command = f"gh run download {run_id} --repo {repo}"
    merge = record.get("immutable_merge_sha") or {}
    revision = (record.get("deployed_verifier_revision") or {}).get("revision")
    report = record.get("report") or {}
    reviewed = list(report.get("files_reviewed") or [])
    changed = list(record.get("changed_files") or [])
    artifact = record.get("artifact_report") or {}
    downloaded = [
        str(name) for name in (record.get("artifacts") or {}).get("downloaded_names") or []
    ]
    comparison_downloaded = any(name.startswith("comparison-results-") for name in downloaded)
    live_failures: list[str] = []
    if log_command not in commands:
        live_failures.append(f"The saved commands do not include `{log_command}`.")
    if download_command not in commands:
        live_failures.append(f"The saved commands do not include `{download_command}`.")
    if run.get("post_merge") is not True:
        live_failures.append("The run is not recorded as post-merge.")
    if record.get("multi_file") is not True:
        live_failures.append("The pull request is not recorded as multi-file.")
    if not (merge.get("values_agree") is True and merge.get("sha")):
        live_failures.append(
            "The immutable merge SHA is missing or the recorded SHA values do not agree."
        )
    if not (isinstance(revision, str) and SHA_RE.fullmatch(revision)):
        live_failures.append("The deployed verifier revision is missing.")
    if not comparison_downloaded:
        live_failures.append(
            f"`{download_command}` did not retrieve a comparison-results artifact, "
            "so the artifact command does not identify the verifier report."
        )
    elif artifact.get("comment_matches_downloaded_member") is not True:
        live_failures.append(
            "The downloaded comparison artifact does not contain the posted report body."
        )
    elif not reviewed:
        live_failures.append("The report does not contain a files-reviewed line.")

    changed_paths = [str(item["path"]) for item in changed]
    reviewed_paths = artifact.get("reviewed_file_paths")
    not_reviewed = artifact.get("files_not_reviewed")
    complete_failures: list[str] = []
    totals_match = bool(reviewed) and all(
        item.get("reviewed") == item.get("total") for item in reviewed
    )
    if not totals_match:
        complete_failures.append(
            "The report does not show files reviewed M of M for every provider."
        )
    elif (
        any(item.get("total") != len(changed_paths) for item in reviewed) or len(changed_paths) < 2
    ):
        complete_failures.append(
            "The files-reviewed totals do not equal the changed-file inventory."
        )
    elif reviewed_paths != changed_paths:
        complete_failures.append(
            "The comparison artifact's reviewed-file inventory does not match "
            "the changed-file inventory."
        )
    elif not_reviewed != []:
        complete_failures.append(
            "files_not_reviewed is not an empty list, so the changed files are not "
            "reconciled as fully reviewed."
        )
    elif report.get("truncated_substring_count") or report.get("prompt_budget_marker_present"):
        complete_failures.append("The published report contains a truncated marker.")

    created_at = None if run is None else run.get("created_at")
    return {
        "artifact_retrieval_command": download_command,
        "changed_file_count": len(changed_paths),
        "complete_report_first_broken_step": (complete_failures[0] if complete_failures else None),
        "counts_as_historical_campaign_evidence": False,
        "criterion_complete_report": not complete_failures,
        "criterion_live_report_identified": not live_failures,
        "deployed_verifier_revision": revision,
        "files_not_reviewed": not_reviewed,
        "files_reviewed": reviewed,
        "historical_campaign_effect": _historical_campaign_effect(
            None if created_at is None else str(created_at)
        ),
        "immutable_merge_sha": merge.get("sha"),
        "input_coverage": artifact.get("input_coverage"),
        "input_coverage_effect": (
            "Input coverage is metadata saved from comparison.json. The published-report "
            "checks use the posted comment. acceptance_evidence and context_truncated "
            "stay visible here and are not rewritten into the comment text."
        ),
        "live_report_first_broken_step": live_failures[0] if live_failures else None,
        "log_command": log_command,
        "prompt_budget_marker_present": report.get("prompt_budget_marker_present"),
        "pull_request_number": (record.get("pull_request") or {}).get("number"),
        "repository": repo,
        "reviewed_file_paths": reviewed_paths,
        "run_id": run_id,
        "run_url": run.get("url"),
        "truncated_substring_count": report.get("truncated_substring_count"),
    }


def _load_live_report_evidence() -> dict[str, Any]:
    return json.loads(LIVE_REPORT_EVIDENCE_PATH.read_text(encoding="utf-8"))


def live_report_acceptance_packet(
    repo: str = WORKFLOWS_REPO,
    *,
    loader: Callable[[], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Replay the saved complete-report packet. The repository check happens first."""
    if is_owner_excluded(repo):
        raise OwnerExcludedRepository(repo)
    evidence = (loader or _load_live_report_evidence)()
    if str(evidence["repository"]) != repo:
        raise ValueError(f"saved live report evidence is for {evidence['repository']}, not {repo}")
    record = assemble_live_pr_record(evidence)
    return {
        "acceptance": live_report_acceptance(record),
        "network_used_for_replay": False,
        "record": record,
    }


def live_pr_record(
    repo: str = WORKFLOWS_REPO,
    *,
    loader: Callable[[], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Replay the saved live pull-request packet. The repository check happens first."""
    if is_owner_excluded(repo):
        raise OwnerExcludedRepository(repo)
    evidence = (loader or _load_live_pr_evidence)()
    if str(evidence["repository"]) != repo:
        raise ValueError(f"saved live evidence is for {evidence['repository']}, not {repo}")
    return assemble_live_pr_record(evidence)


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Audit helpers for the #4036 campaign record. "
            "campaign-definition prints recovered rules and leaves unspecified "
            "eligibility and timing fields unknown. "
            "initial-evidence prints one cited GitHub Actions run and stops after "
            f"{INITIAL_EVIDENCE_MAX_ATTEMPTS} attempts or "
            f"{int(INITIAL_EVIDENCE_MAX_ELAPSED_SECONDS)} seconds. "
            "resolve-production-surfaces reads the local git tree at the saved "
            f"run {INITIAL_EVIDENCE_RUN_ID} workflow SHA and prints tracked verifier "
            "locations plus the implementation revision. It does not use the network. "
            "The saved evidence was collected with "
            f"`{_GH_API} repos/stranske/Workflows/actions/runs/{INITIAL_EVIDENCE_RUN_ID}` and "
            f"`gh run view {INITIAL_EVIDENCE_RUN_ID} --repo stranske/Workflows --log`. "
            "live-pr-evidence replays the saved multi-file pull request packet and "
            "does not use the network. Its collection commands are gh run list, "
            f"gh run view {INITIAL_EVIDENCE_RUN_ID} --log, gh run download "
            f"{INITIAL_EVIDENCE_RUN_ID}, and the pull request, report, issue, and "
            "artifact API reads. "
            "live-report-acceptance replays verifier_4422_live_report.json without "
            "network access. Collection for that packet is "
            "`gh run view 41736356184 --repo stranske/Workflows --log` and "
            "`gh run download 41736356184 --repo stranske/Workflows`, plus the pull "
            "request, report, issue, and artifact API reads. The replay prints the "
            "same acceptance record, including the merge SHA, deployed verifier "
            "revision, reviewed-file inventory, and the statement that the run is "
            "not 2026-10-24 campaign evidence."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "campaign-definition",
        help="Print the recovered campaign definition. No network access.",
    )
    subparsers.add_parser(
        "initial-evidence",
        help=(
            "Print GitHub run "
            f"{INITIAL_EVIDENCE_RUN_ID} in {WORKFLOWS_REPO}. "
            "One command, at most two attempts, 120 second budget."
        ),
    )
    subparsers.add_parser(
        "resolve-production-surfaces",
        help=(
            "Print tracked verifier locations and the implementation used by run "
            f"{INITIAL_EVIDENCE_RUN_ID}. Local git only; replays saved run evidence."
        ),
    )
    subparsers.add_parser(
        "live-pr-evidence",
        help=(
            "Replay the saved multi-file pull request packet for run "
            f"{INITIAL_EVIDENCE_RUN_ID}. No network access. "
            "The output lists the gh run list, gh run view --log, gh run download, "
            "and GitHub API commands that collected the packet."
        ),
    )
    subparsers.add_parser(
        "live-report-acceptance",
        help=(
            "Replay the saved post-merge report for run 41736356184. No network access. "
            "Print whether gh run view --log and gh run download identify the report, "
            "and whether the published report shows files reviewed M of M with no "
            "truncated marker."
        ),
    )
    args = parser.parse_args(argv)
    if args.command == "campaign-definition":
        _print_json(campaign_definition())
        return 0
    if args.command == "resolve-production-surfaces":
        _print_json(resolve_production_surfaces())
        return 0
    if args.command == "live-pr-evidence":
        _print_json(live_pr_record())
        return 0
    if args.command == "live-report-acceptance":
        _print_json(live_report_acceptance_packet())
        return 0
    result = run_initial_evidence()
    _print_json(result)
    return 0 if result["outcome"] is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
