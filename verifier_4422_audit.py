#!/usr/bin/env python3
"""Recovered #4036 campaign record and the first bounded evidence check for #4422.

Unknown eligibility and timing rules stay unknown. This module does not query the
owner-excluded repository and does not treat later verifier runs as the 2026-10-24 result.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from collections.abc import Callable, Sequence
from typing import Any

from scripts.list_registered_consumer_repos import is_owner_excluded

UNKNOWN = "unknown"
WORKFLOWS_REPO = "stranske/Workflows"
INITIAL_EVIDENCE_RUN_ID = "39090617832"
INITIAL_EVIDENCE_MAX_ATTEMPTS = 2
INITIAL_EVIDENCE_MAX_ELAPSED_SECONDS = 120.0
INITIAL_EVIDENCE_ATTEMPT_TIMEOUT_SECONDS = 90.0

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


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit helpers for the #4036 campaign record. "
            "campaign-definition prints recovered rules and leaves unspecified "
            "eligibility and timing fields unknown. "
            "initial-evidence prints one cited GitHub Actions run and stops after "
            f"{INITIAL_EVIDENCE_MAX_ATTEMPTS} attempts or "
            f"{int(INITIAL_EVIDENCE_MAX_ELAPSED_SECONDS)} seconds."
        )
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
    args = parser.parse_args(argv)
    if args.command == "campaign-definition":
        _print_json(campaign_definition())
        return 0
    result = run_initial_evidence()
    _print_json(result)
    return 0 if result["outcome"] is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
