"""Publish and validate the exact verifier decision used by corpus harvesting."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

MARKER = "verifier-corpus-decision/v1"


def decision_from_results(
    results: list[dict[str, Any]], identity: dict[str, str]
) -> dict[str, Any] | None:
    """Retain usable provider decisions; infrastructure errors are not ground truth."""
    verdicts = [str(result.get("verdict", "")).upper() for result in results]
    if not results or not all(result.get("used_llm") for result in results):
        return None
    if any(verdict not in {"PASS", "CONCERNS", "FAIL", "NON_PASS"} for verdict in verdicts):
        return None
    return {
        "schema": MARKER,
        **identity,
        "verdict": "PASS" if all(verdict == "PASS" for verdict in verdicts) else "NON_PASS",
        "provider_verdicts": verdicts,
    }


def joined_decision(record: dict[str, Any]) -> dict[str, Any] | None:
    """Require a decision tied to this repository, PR, head and evaluated merge."""
    decision = record.get("verifier_decision")
    if not isinstance(decision, dict) or decision.get("schema") != MARKER:
        return None
    repo = str(record.get("repo", "")).strip().lower()
    pr = str(record.get("pr", ""))
    head = str(record.get("head_sha", ""))
    evaluated = str(record.get("merge_sha") or head)
    run = str(decision.get("run_id", ""))
    attempt = str(decision.get("run_attempt", ""))
    if (
        not re.fullmatch(r"[^/\s]+/[^/\s]+", repo)
        or not pr.isdigit()
        or not re.fullmatch(r"[0-9a-f]{40}", head)
        or not re.fullmatch(r"[0-9a-f]{40}", evaluated)
        or not run.isdigit()
        or not attempt.isdigit()
        or int(run) < 1
        or int(attempt) < 1
        or str(decision.get("repo", "")).lower() != repo
        or str(decision.get("pr", "")) != pr
        or decision.get("head_sha") != head
        or decision.get("evaluated_sha") != evaluated
        or decision.get("verdict") not in {"PASS", "NON_PASS"}
        or not str(decision.get("source_url", ""))
        .lower()
        .startswith(f"https://github.com/{repo}/pull/{pr}#issuecomment-")
    ):
        return None
    return decision


def decision_from_comments(
    record: dict[str, Any], comments: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Read only the verifier bot's structured evidence, newest usable record first."""
    for comment in reversed(comments):
        if (comment.get("author") or {}).get("login") not in {
            "github-actions",
            "github-actions[bot]",
        }:
            continue
        matches = re.findall(
            r"<!-- verifier-corpus-decision/v1 (\{[^\n]+\}) -->", comment.get("body", "")
        )
        for match in reversed(matches):
            try:
                decision = json.loads(match)
            except json.JSONDecodeError:
                continue
            if not isinstance(decision, dict):
                continue
            decision["source_url"] = comment.get("url", "")
            if joined_decision({**record, "verifier_decision": decision}):
                return decision
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--comment", type=Path, required=True)
    args = parser.parse_args(argv)
    identity = {
        key: os.environ.get(env, "")
        for key, env in {
            "repo": "GITHUB_REPOSITORY",
            "pr": "PR_NUMBER",
            "head_sha": "PR_HEAD_SHA",
            "evaluated_sha": "EVALUATED_SHA",
            "run_id": "GITHUB_RUN_ID",
            "run_attempt": "GITHUB_RUN_ATTEMPT",
        }.items()
    }
    results = json.loads(args.comparison.read_text(encoding="utf-8")).get("results", [])
    decision = decision_from_results(results, identity)
    if decision:
        with args.comment.open("a", encoding="utf-8") as handle:
            handle.write(f"\n<!-- {MARKER} {json.dumps(decision, sort_keys=True)} -->\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
