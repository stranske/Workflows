"""Validators for round-2 negotiation outputs.

Two artifacts:

1. Per-agent per-turn output (one file per agent per turn).
2. Converged set (one file per repo, written after all turns complete).

The contract is documented in `docs/ops/REPO_REVIEW_ROUND2_SCHEMA.md`.

The validator is deliberately strict on the meta-candidate's substance fields
(scope=audit, audit-report acceptance, anti-bundling non-goal) because the
meta-candidate is the highest-leverage and highest-risk shape in the protocol:
it can either save scattered work or balloon into an unbounded refactor PR.
The schema gate is what keeps it in the audit-and-plan lane.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ALLOWED_AGENTS = {"codex", "claude"}
ALLOWED_MARKS = {
    "agree-keep",
    "agree-merge",
    "disagree-drop",
    "disagree-revise",
    "abstain",
}
ALLOWED_PRIORITIES = {"high", "normal", "low"}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}
ALLOWED_SCOPES = {"fix", "audit"}

REASON_MIN_CHARS = 30
META_TASKS_MIN = 3
META_ACCEPTANCE_MIN = 3
META_NON_GOALS_MIN = 1

META_ACCEPTANCE_TOKENS = (
    "report",
    "artifact",
    "follow-up",
    "follow up",
    "issue",
    "audit",
)
META_NON_GOAL_TOKENS = (
    "bundle",
    "single pr",
    "not bundle",
    "per-instance",
    "ship separately",
    "do not bundle",
)


def _is_str(value: Any) -> bool:
    return isinstance(value, str)


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_str_list(value: Any, min_items: int = 1) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= min_items
        and all(_is_nonempty_str(item) for item in value)
    )


def _is_allowed_agent(value: Any) -> bool:
    if not _is_nonempty_str(value):
        return False
    return value in ALLOWED_AGENTS or str(value).startswith("pilot-")


def validate_mark(mark: Any, index: int) -> list[str]:
    errors: list[str] = []
    prefix = f"marks[{index}]"
    if not isinstance(mark, dict):
        return [f"{prefix}: must be an object"]

    if not _is_allowed_agent(mark.get("source_agent")):
        errors.append(
            f"{prefix}.source_agent: must be one of {sorted(ALLOWED_AGENTS)} or 'pilot-*'"
        )

    if not isinstance(mark.get("candidate_index"), int):
        errors.append(f"{prefix}.candidate_index: must be an integer")

    mark_value = mark.get("mark")
    if mark_value not in ALLOWED_MARKS:
        errors.append(f"{prefix}.mark: must be one of {sorted(ALLOWED_MARKS)} (got {mark_value!r})")

    reason = mark.get("reason", "")
    if not _is_nonempty_str(reason):
        errors.append(f"{prefix}.reason: must be a non-empty string")
    elif len(reason.strip()) < REASON_MIN_CHARS:
        errors.append(
            f"{prefix}.reason: must be ≥{REASON_MIN_CHARS} chars (got {len(reason.strip())})"
        )

    if mark_value == "agree-merge" and not isinstance(mark.get("merge_proposal"), dict):
        errors.append(f"{prefix}.merge_proposal: required when mark is 'agree-merge'")

    if mark_value == "disagree-revise" and not isinstance(mark.get("revision_proposal"), dict):
        errors.append(f"{prefix}.revision_proposal: required when mark is 'disagree-revise'")

    if mark_value == "disagree-drop":
        # Drop reasons must cite a file ref / test ref / issue / PR.
        # Heuristic: look for a file extension, a slash path, '#NNNN', or
        # 'tests/' / 'PR' / 'issue' tokens.
        lowered = reason.lower()
        cited = (
            bool(re.search(r"\.(py|js|ts|tsx|md|json|yml|yaml|sql|sh)\b", lowered))
            or "/" in lowered
            or bool(re.search(r"#\d+", lowered))
            or "tests/" in lowered
            or "pr " in lowered
            or "issue" in lowered
            or "merged" in lowered
        )
        if not cited:
            errors.append(
                f"{prefix}.reason: 'disagree-drop' must cite a file ref, test ref, "
                "open issue, or merged PR; bare prose is not enough."
            )

    return errors


def validate_meta_candidate(meta: Any) -> list[str]:
    errors: list[str] = []
    prefix = "meta_candidate_proposal"
    if not isinstance(meta, dict):
        return [f'{prefix}: must be an object (use {{"proposed": false}} when no pattern)']

    proposed = meta.get("proposed")
    if not isinstance(proposed, bool):
        errors.append(f"{prefix}.proposed: must be a boolean")
        return errors

    if not proposed:
        # Nothing else required.
        return errors

    for field in ("pattern", "title", "rationale"):
        if not _is_nonempty_str(meta.get(field)):
            errors.append(f"{prefix}.{field}: must be a non-empty string when proposed=true")

    supporting = meta.get("supporting_candidate_indexes")
    if not isinstance(supporting, list) or len(supporting) < 2:
        errors.append(f"{prefix}.supporting_candidate_indexes: must list ≥2 anchoring candidates")
    else:
        for sub_idx, item in enumerate(supporting):
            sub_prefix = f"{prefix}.supporting_candidate_indexes[{sub_idx}]"
            if not isinstance(item, dict):
                errors.append(f"{sub_prefix}: must be an object")
                continue
            if not _is_allowed_agent(item.get("agent")):
                errors.append(f"{sub_prefix}.agent: must be a known agent identifier")
            if not isinstance(item.get("candidate_index"), int):
                errors.append(f"{sub_prefix}.candidate_index: must be an integer")

    scope = meta.get("scope")
    if scope != "audit":
        errors.append(
            f"{prefix}.scope: must be exactly 'audit' for a meta-candidate "
            f"(got {scope!r}); fixes ship as per-instance candidates."
        )

    tasks = meta.get("tasks")
    if not _is_str_list(tasks, min_items=META_TASKS_MIN):
        errors.append(
            f"{prefix}.tasks: must list ≥{META_TASKS_MIN} concrete steps "
            "(enumerate, classify, file follow-up issues)"
        )

    acceptance = meta.get("acceptance_criteria")
    if not _is_str_list(acceptance, min_items=META_ACCEPTANCE_MIN):
        errors.append(f"{prefix}.acceptance_criteria: must list ≥{META_ACCEPTANCE_MIN} criteria")
    else:
        joined = " ".join(str(c).lower() for c in acceptance)
        if not any(token in joined for token in META_ACCEPTANCE_TOKENS):
            errors.append(
                f"{prefix}.acceptance_criteria: at least one criterion must reference an "
                "audit report artifact or per-instance follow-up issue filing."
            )

    non_goals = meta.get("non_goals")
    if not _is_str_list(non_goals, min_items=META_NON_GOALS_MIN):
        errors.append(f"{prefix}.non_goals: must list ≥{META_NON_GOALS_MIN} non-goals")
    else:
        joined = " ".join(str(n).lower() for n in non_goals)
        if not any(token in joined for token in META_NON_GOAL_TOKENS):
            errors.append(
                f"{prefix}.non_goals: must explicitly forbid bundling per-instance fixes "
                'into a single PR (e.g., "Do not bundle per-instance fixes into a single PR").'
            )

    priority = meta.get("priority")
    if priority not in {"normal", "low"}:
        errors.append(
            f"{prefix}.priority: must be 'normal' or 'low' (high reserved for "
            f"per-instance fixes; got {priority!r})"
        )

    confidence = meta.get("confidence")
    if confidence not in ALLOWED_CONFIDENCE:
        errors.append(f"{prefix}.confidence: must be one of {sorted(ALLOWED_CONFIDENCE)}")
    elif confidence == "high" and isinstance(supporting, list) and len(supporting) < 4:
        errors.append(
            f"{prefix}.confidence: 'high' requires ≥4 supporting per-instance candidates "
            f"(got {len(supporting)}); use 'medium' or 'low'."
        )

    return errors


def validate_turn_output(data: Any, *, expected_repo: str | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["turn output: top-level must be an object"]

    if not _is_allowed_agent(data.get("agent")):
        errors.append("agent: must be a known agent identifier")
    repo = data.get("repo")
    if not _is_nonempty_str(repo) or "/" not in str(repo):
        errors.append("repo: must be in 'owner/name' form")
    elif expected_repo is not None and str(repo) != expected_repo:
        errors.append(f"repo: expected {expected_repo!r} got {repo!r}")

    turn = data.get("turn")
    if not isinstance(turn, int) or turn not in (1, 2, 3):
        errors.append("turn: must be 1, 2, or 3")

    marks = data.get("marks")
    if not isinstance(marks, list):
        errors.append("marks: must be a list")
        marks = []
    elif not marks:
        errors.append("marks: must be non-empty (one entry per round-1 candidate from both agents)")
    else:
        for index, mark in enumerate(marks):
            errors.extend(validate_mark(mark, index))

    revisions = data.get("own_candidates_revisions", [])
    if not isinstance(revisions, list):
        errors.append("own_candidates_revisions: must be a list (may be empty)")

    errors.extend(validate_meta_candidate(data.get("meta_candidate_proposal")))

    return errors


def validate_converged_set(data: Any, *, expected_repo: str | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["converged set: top-level must be an object"]

    if data.get("schema_version") != "v1":
        errors.append("schema_version: must be 'v1'")

    repo = data.get("repo")
    if not _is_nonempty_str(repo) or "/" not in str(repo):
        errors.append("repo: must be in 'owner/name' form")
    elif expected_repo is not None and str(repo) != expected_repo:
        errors.append(f"repo: expected {expected_repo!r} got {repo!r}")

    if not isinstance(data.get("turns_completed"), int):
        errors.append("turns_completed: must be an integer")

    sources = data.get("round1_sources")
    if not isinstance(sources, list) or not sources:
        errors.append("round1_sources: must be a non-empty list")

    converged = data.get("converged_candidates")
    if not isinstance(converged, list):
        errors.append("converged_candidates: must be a list (may be empty)")
        converged = []
    for index, candidate in enumerate(converged):
        if not isinstance(candidate, dict):
            errors.append(f"converged_candidates[{index}]: must be an object")
            continue
        scope = candidate.get("scope", "fix")
        if scope not in ALLOWED_SCOPES:
            errors.append(
                f"converged_candidates[{index}].scope: must be one of {sorted(ALLOWED_SCOPES)}"
            )

    if not isinstance(data.get("deadlocked_candidates"), list):
        errors.append("deadlocked_candidates: must be a list (may be empty)")
    if not isinstance(data.get("dropped_candidates"), list):
        errors.append("dropped_candidates: must be a list (may be empty)")

    meta = data.get("meta_candidate")
    if meta is not None and not isinstance(meta, dict):
        errors.append("meta_candidate: must be null or an object")

    log = data.get("negotiation_log")
    if not isinstance(log, list):
        errors.append("negotiation_log: must be a list")

    return errors


def validate_turn_output_file(path: Path, *, expected_repo: str | None = None) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"turn file: cannot read {path}: {exc}"]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [f"turn file: invalid JSON in {path}: {exc}"]
    return validate_turn_output(data, expected_repo=expected_repo)


def validate_converged_set_file(path: Path, *, expected_repo: str | None = None) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"converged file: cannot read {path}: {exc}"]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [f"converged file: invalid JSON in {path}: {exc}"]
    return validate_converged_set(data, expected_repo=expected_repo)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Round-2 turn output OR converged.json files.")
    parser.add_argument(
        "--expected-repo", default=None, help="Optional expected repo (owner/name)."
    )
    parser.add_argument(
        "--converged",
        action="store_true",
        help="Validate as converged.json instead of per-turn output.",
    )
    args = parser.parse_args()

    overall = 0
    for raw_path in args.paths:
        path = Path(raw_path)
        if args.converged:
            errors = validate_converged_set_file(path, expected_repo=args.expected_repo)
        else:
            errors = validate_turn_output_file(path, expected_repo=args.expected_repo)
        if errors:
            overall += len(errors)
            print(f"{path}: {len(errors)} error(s):")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"{path}: OK")
    return 1 if overall else 0


if __name__ == "__main__":
    raise SystemExit(main())
