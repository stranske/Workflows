"""Publish and validate the exact verifier decision used by corpus harvesting."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

MARKER = "verifier-corpus-decision/v1"


def event_metadata(path: Path) -> dict[str, Any]:
    """Read only the collector's exact event, never a caller-provided digest."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    event = manifest["verification_event"]
    fields = (
        "schema",
        "repo",
        "pr",
        "head_sha",
        "evaluated_sha",
        "request_sha256",
        "material_sha256",
    )
    core = {key: event[key] for key in fields}
    actual = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if (
        event.get("schema") != "verification-event/v1"
        or actual != event.get("event_id")
        or not re.fullmatch(r"[0-9a-f]{40}", str(event.get("head_sha")))
        or not re.fullmatch(r"[0-9a-f]{40}", str(event.get("evaluated_sha")))
        or any(
            not re.fullmatch(r"[0-9a-f]{64}", str(event.get(key)))
            for key in ("request_sha256", "material_sha256")
        )
    ):
        raise ValueError("Invalid collector verification event")
    metadata = {"verification_event": event, "assessment_identity": manifest["assessment_identity"]}
    predecessor = manifest.get("predecessor_event_id")
    if predecessor:
        if not re.fullmatch(r"[0-9a-f]{64}", str(predecessor)):
            raise ValueError("Invalid verification predecessor")
        metadata["predecessor_event_id"] = predecessor
    return metadata


def decision_from_results(
    results: list[dict[str, Any]], identity: dict[str, str], *, ci_failed: str | None = None
) -> dict[str, Any] | None:
    """Retain usable decisions with the workflow's trusted merge-CI hard gate."""
    verdicts = [str(result.get("verdict", "")).upper() for result in results]
    if not results or not all(
        result.get("used_llm") is True and not result.get("error") for result in results
    ):
        return None
    if any(verdict not in {"PASS", "CONCERNS", "FAIL", "NON_PASS"} for verdict in verdicts):
        return None
    # The context step emits exactly true/false. Missing or malformed context
    # cannot establish an authoritative disposition for corpus harvesting.
    if ci_failed not in {"true", "false"}:
        return None
    return {
        "schema": MARKER,
        **identity,
        "verdict": (
            "PASS" if ci_failed == "false" and all(v == "PASS" for v in verdicts) else "NON_PASS"
        ),
        "ci_failed": ci_failed == "true",
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
        or (decision.get("ci_failed") is True and decision.get("verdict") == "PASS")
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
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--comparison", type=Path)
    inputs.add_argument("--evaluation", type=Path)
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
    payload = json.loads((args.comparison or args.evaluation).read_text(encoding="utf-8"))
    results = payload.get("results", []) if args.comparison else [payload]
    decision = decision_from_results(results, identity, ci_failed=os.environ.get("CI_FAILED"))
    if decision:
        manifest = Path("verification-event-manifest.json")
        if manifest.exists():
            metadata = event_metadata(manifest)
            event = metadata["verification_event"]
            if any(
                str(event[key]).lower() != str(identity[key]).lower()
                for key in ("repo", "pr", "head_sha", "evaluated_sha")
            ):
                raise ValueError("Collector event differs from terminal result identity")
            decision.update(metadata)
        with args.comment.open("a", encoding="utf-8") as handle:
            handle.write(f"\n<!-- {MARKER} {json.dumps(decision, sort_keys=True)} -->\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
