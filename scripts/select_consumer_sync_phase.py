#!/usr/bin/env python3
"""Select a plan-bound preview, canary, or promotion matrix for Maint 68.

The selector is deliberately read-only.  It turns the already compiled manifest
plan into prospective per-repository evidence, and only permits the promote
matrix when every configured canary has current, green, review-clear evidence
for the exact same plan ID.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.sync_manifest_compiler import PLAN_SCHEMA
except ImportError:
    from sync_manifest_compiler import PLAN_SCHEMA  # type: ignore[no-redef]

CANARY_SCHEMA = "workflows.consumer-sync-canaries/v1"
PHASES = {"preview", "canary", "promote"}


class PhaseSelectionError(ValueError):
    """The requested phase cannot safely construct a write matrix."""


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PhaseSelectionError(f"invalid_json:{path}") from exc


def _parse_repos(raw: str) -> list[str]:
    repos = [repo.strip() for repo in raw.split(",") if repo.strip()]
    if not repos or len(repos) != len(set(repos)):
        raise PhaseSelectionError("registered_repos_must_be_nonempty_and_unique")
    return repos


def _load_canaries(path: Path, registered_repos: list[str]) -> list[dict[str, Any]]:
    config = _read_json(path)
    if not isinstance(config, dict) or config.get("schema") != CANARY_SCHEMA:
        raise PhaseSelectionError("unsupported_canary_config_schema")
    canaries = config.get("canaries")
    if not isinstance(canaries, list) or not 2 <= len(canaries) <= 3:
        raise PhaseSelectionError("canary_config_requires_two_or_three_repos")
    repos: list[str] = []
    normalized: list[dict[str, Any]] = []
    for item in canaries:
        if not isinstance(item, dict):
            raise PhaseSelectionError("invalid_canary_entry")
        repo = item.get("repo")
        capabilities = item.get("capabilities")
        if (
            not isinstance(repo, str)
            or repo not in registered_repos
            or not isinstance(capabilities, list)
            or not capabilities
            or not all(isinstance(capability, str) and capability for capability in capabilities)
        ):
            raise PhaseSelectionError("invalid_canary_entry")
        repos.append(repo)
        normalized.append({"repo": repo, "capabilities": sorted(capabilities)})
    if len(repos) != len(set(repos)):
        raise PhaseSelectionError("duplicate_canary_repo")
    return normalized


def _validate_plan(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA:
        raise PhaseSelectionError("unsupported_consumer_sync_plan")
    if not isinstance(plan.get("plan_id"), str) or not plan["plan_id"].startswith("sha256:"):
        raise PhaseSelectionError("invalid_consumer_sync_plan_id")
    entries = plan.get("entries")
    removals = plan.get("removals")
    if not isinstance(entries, list) or not isinstance(removals, list):
        raise PhaseSelectionError("invalid_consumer_sync_plan_collections")
    return plan


def _evidence_rows(raw: str) -> list[dict[str, Any]]:
    if not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PhaseSelectionError("invalid_canary_evidence_json") from exc
    if isinstance(parsed, dict):
        parsed = parsed.get("results")
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        raise PhaseSelectionError("invalid_canary_evidence_json")
    return parsed


def _promotion_rejections(
    *, plan_id: str, canary_repos: list[str], evidence: list[dict[str, Any]]
) -> list[str]:
    by_repo: dict[str, dict[str, Any]] = {}
    reasons: list[str] = []
    for item in evidence:
        repo = str(item.get("repo", ""))
        if repo in canary_repos and repo in by_repo:
            reasons.append(f"duplicate_canary_evidence:{repo}")
            continue
        by_repo[repo] = item
    for repo in canary_repos:
        item = by_repo.get(repo)
        if item is None:
            reasons.append(f"missing_canary_evidence:{repo}")
            continue
        if item.get("plan_id") != plan_id:
            reasons.append(f"stale_or_mixed_plan:{repo}")
        if item.get("required_check_state") != "success":
            reasons.append(f"required_checks_not_green:{repo}")
        if item.get("active_review_thread_count") != 0:
            reasons.append(f"active_review_debt:{repo}")
    return reasons


def select_phase(
    plan: Any,
    *,
    phase: str,
    registered_repos: list[str],
    canaries: list[dict[str, Any]],
    evidence: list[dict[str, Any]] | None = None,
    selected_repos: list[str] | None = None,
) -> dict[str, Any]:
    """Return a deterministic matrix plus the evidence needed to audit it."""
    if phase not in PHASES:
        raise PhaseSelectionError("unsupported_sync_phase")
    plan = _validate_plan(plan)
    canary_repos = [item["repo"] for item in canaries]
    if selected_repos is not None and not set(selected_repos) <= set(registered_repos):
        raise PhaseSelectionError("selected_repos_must_be_registered")
    target_repos = selected_repos if selected_repos is not None else registered_repos
    paths = sorted(
        {str(entry.get("target")) for entry in plan["entries"] if entry.get("target")}
        | {str(removal.get("target")) for removal in plan["removals"] if removal.get("target")}
    )
    prospective = [
        {
            "repo": repo,
            "desired_hash": plan["plan_id"],
            "affected_paths": paths,
            "canary": repo in canary_repos,
        }
        for repo in target_repos
    ]
    if phase == "preview":
        selected = []
    elif phase == "canary":
        selected = target_repos if selected_repos is not None else canary_repos
    else:
        reasons = _promotion_rejections(
            plan_id=plan["plan_id"],
            canary_repos=canary_repos,
            evidence=evidence or [],
        )
        if reasons:
            raise PhaseSelectionError("promotion_rejected:" + ",".join(reasons))
        selected = [repo for repo in target_repos if repo not in canary_repos]
    return {
        "schema": "workflows.consumer-sync-phase-selection/v1",
        "version": 1,
        "phase": phase,
        "plan_id": plan["plan_id"],
        "canaries": canaries,
        "selected_repos": selected,
        "matrix": {"repo": selected},
        "prospective_diffs": prospective,
        "promotion_allowed": phase == "promote",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--phase", choices=sorted(PHASES), required=True)
    parser.add_argument("--registered-repos", required=True)
    parser.add_argument("--selected-repos", default="")
    parser.add_argument("--canaries", type=Path, required=True)
    parser.add_argument("--canary-evidence-json", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = select_phase(
            _read_json(args.plan),
            phase=args.phase,
            registered_repos=_parse_repos(args.registered_repos),
            canaries=_load_canaries(args.canaries, _parse_repos(args.registered_repos)),
            evidence=_evidence_rows(args.canary_evidence_json),
            selected_repos=_parse_repos(args.selected_repos) if args.selected_repos else None,
        )
    except PhaseSelectionError as exc:
        parser.error(str(exc))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
