"""Validator for round-1 reviewer findings.

The contract this validator enforces is documented in
`docs/ops/REPO_REVIEW_ROUND1_SCHEMA.md`. Findings live at
`<output_dir>/round1/<agent>/<repo_safe>/findings.json`.

The validator is intentionally strict on the substance fields (design summary,
readiness summary, evidence refs, candidate evidence traces) because the
fundamental failure mode of the prior automation was generic / template-shaped
output that passed structural checks but did not constitute a real review.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ALLOWED_AGENTS = {"codex", "claude"}
ALLOWED_IMPL_STATUS = {
    "implemented-and-verified",
    "partial",
    "missing",
    "stale-or-conflicting",
}
ALLOWED_PRIORITIES = {"high", "normal", "low"}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}

DESIGN_SUMMARY_MIN_CHARS = 120
READINESS_SUMMARY_MIN_CHARS = 120
GAP_FIELD_MIN_CHARS = 40

GENERIC_SUMMARY_PHRASES = (
    "ready for normal coding-agent implementation",
    "ready for normal coding agent",
    "review run-time before approving",
    "review the candidate set",
    "no completed semantic",
    "implementation-heavy and test-heavy",
    "the repo has been reviewed",
    "review the standard semantic review prompt",
)
GENERIC_GAP_PHRASES = (
    "implementation is incomplete",
    "code does not match design",
    "needs more work",
    "should be improved",
)
WORKFLOWS_MISROUTE_TOKENS = (
    "workflow sync",
    "workflow-sync",
    "template sync",
    "template-sync",
    "agents.md sync",
    "claude.md sync",
    "lane management",
    "lane-management",
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


def _has_generic_phrase(text: str, phrases: tuple[str, ...]) -> str | None:
    lowered = text.lower()
    for phrase in phrases:
        if phrase in lowered:
            return phrase
    return None


def validate_implementation_piece(piece: Any, index: int) -> list[str]:
    errors: list[str] = []
    prefix = f"implementation_classification[{index}]"
    if not isinstance(piece, dict):
        return [f"{prefix}: must be an object"]
    if not _is_nonempty_str(piece.get("piece")):
        errors.append(f"{prefix}.piece: must be a non-empty string")
    status = piece.get("status")
    if not _is_str(status) or status not in ALLOWED_IMPL_STATUS:
        errors.append(
            f"{prefix}.status: must be one of {sorted(ALLOWED_IMPL_STATUS)} (got {status!r})"
        )
    evidence = piece.get("evidence")
    if not _is_str_list(evidence, min_items=1):
        errors.append(f"{prefix}.evidence: must be a non-empty list of strings")
    return errors


def _looks_like_repo_relative_path(value: str) -> bool:
    """Heuristic: does this string look like a file ref the agent claims to have inspected?"""
    if not value:
        return False
    if value.startswith(("http://", "https://")):
        return False
    if " " in value.strip():
        # Allow a single optional ":line" or "#section" suffix; otherwise strings
        # with internal whitespace are usually prose, not refs.
        return False
    return bool(re.search(r"[A-Za-z0-9_./\\-]", value))


def validate_candidate(candidate: Any, index: int) -> list[str]:
    errors: list[str] = []
    prefix = f"candidates[{index}]"
    if not isinstance(candidate, dict):
        return [f"{prefix}: must be an object"]

    title = candidate.get("title", "")
    if not _is_nonempty_str(title):
        errors.append(f"{prefix}.title: must be a non-empty string")
    elif len(title) > 120:
        errors.append(f"{prefix}.title: must be ≤120 chars (got {len(title)})")

    for field in ("gap", "current_state", "required_change"):
        value = candidate.get(field, "")
        if not _is_nonempty_str(value):
            errors.append(f"{prefix}.{field}: must be a non-empty string")
        elif len(value.strip()) < GAP_FIELD_MIN_CHARS:
            errors.append(
                f"{prefix}.{field}: must be ≥{GAP_FIELD_MIN_CHARS} chars "
                f"(got {len(value.strip())})"
            )
        elif _is_nonempty_str(value):
            phrase = _has_generic_phrase(value, GENERIC_GAP_PHRASES)
            if phrase is not None:
                errors.append(
                    f"{prefix}.{field}: contains generic phrase ({phrase!r}); "
                    "be specific about what the design commits to and what the code shows."
                )

    for field in ("design_refs", "implementation_refs", "test_refs"):
        value = candidate.get(field)
        if not _is_str_list(value, min_items=1):
            errors.append(f"{prefix}.{field}: must be a non-empty list of strings")
            continue
        for item_index, item in enumerate(value):
            if not _looks_like_repo_relative_path(item):
                errors.append(
                    f"{prefix}.{field}[{item_index}]: {item!r} does not look like a "
                    "repo-relative file ref; provide a path (with optional :line)."
                )

    acceptance = candidate.get("acceptance_criteria")
    if not _is_str_list(acceptance, min_items=2):
        errors.append(f"{prefix}.acceptance_criteria: must be a list of ≥2 verifiable conditions")
    else:
        joined = " ".join(str(item) for item in acceptance).lower()
        if not any(
            token in joined
            for token in ("test", "smoke", "verifier", "live", "ci", "fail", "assert")
        ):
            errors.append(
                f"{prefix}.acceptance_criteria: at least one criterion must reference a "
                "test, smoke check, verifier run, CI gate, or live-readiness check."
            )

    if not _is_str_list(candidate.get("non_goals"), min_items=1):
        errors.append(f"{prefix}.non_goals: must be a non-empty list of strings")
    if not _is_str_list(candidate.get("tasks"), min_items=2):
        errors.append(f"{prefix}.tasks: must be a list of ≥2 concrete tasks")

    priority = candidate.get("priority")
    if priority not in ALLOWED_PRIORITIES:
        errors.append(
            f"{prefix}.priority: must be one of {sorted(ALLOWED_PRIORITIES)} (got {priority!r})"
        )
    confidence = candidate.get("confidence")
    if confidence not in ALLOWED_CONFIDENCE:
        errors.append(
            f"{prefix}.confidence: must be one of {sorted(ALLOWED_CONFIDENCE)} "
            f"(got {confidence!r})"
        )

    title_lower = str(title).lower()
    for token in WORKFLOWS_MISROUTE_TOKENS:
        if token in title_lower:
            errors.append(
                f"{prefix}.title: looks like Workflows-maintenance work ({token!r}); "
                "route to stranske/Workflows unless this implements repo-local behavior."
            )
            break

    return errors


def validate_findings(data: Any, *, expected_repo: str | None = None) -> list[str]:
    """Return list of validation errors. Empty list means valid."""
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["findings: top-level must be an object"]

    agent = data.get("agent")
    if not _is_nonempty_str(agent):
        errors.append("agent: must be a non-empty string")
    elif agent not in ALLOWED_AGENTS and not str(agent).startswith("pilot-"):
        # Allow pilot- prefix for piloting before production cron.
        errors.append(
            f"agent: must be one of {sorted(ALLOWED_AGENTS)} or start with 'pilot-' "
            f"(got {agent!r})"
        )

    repo = data.get("repo")
    if not _is_nonempty_str(repo):
        errors.append("repo: must be a non-empty string")
    elif "/" not in str(repo):
        errors.append(f"repo: must be in 'owner/name' form (got {repo!r})")
    elif expected_repo is not None and str(repo) != expected_repo:
        errors.append(f"repo: expected {expected_repo!r} but got {repo!r}")

    design_summary = data.get("design_summary", "")
    if not _is_nonempty_str(design_summary):
        errors.append("design_summary: must be a non-empty string")
    elif len(design_summary.strip()) < DESIGN_SUMMARY_MIN_CHARS:
        errors.append(
            f"design_summary: must be ≥{DESIGN_SUMMARY_MIN_CHARS} chars "
            f"(got {len(design_summary.strip())})"
        )
    elif _is_nonempty_str(design_summary):
        phrase = _has_generic_phrase(design_summary, GENERIC_SUMMARY_PHRASES)
        if phrase is not None:
            errors.append(
                f"design_summary: contains generic phrase ({phrase!r}); the design "
                "summary must describe THIS repo's intended product/workflow specifically."
            )

    readiness_summary = data.get("readiness_summary", "")
    if not _is_nonempty_str(readiness_summary):
        errors.append("readiness_summary: must be a non-empty string")
    elif len(readiness_summary.strip()) < READINESS_SUMMARY_MIN_CHARS:
        errors.append(
            f"readiness_summary: must be ≥{READINESS_SUMMARY_MIN_CHARS} chars "
            f"(got {len(readiness_summary.strip())})"
        )
    elif _is_nonempty_str(readiness_summary):
        phrase = _has_generic_phrase(readiness_summary, GENERIC_SUMMARY_PHRASES)
        if phrase is not None:
            errors.append(
                f"readiness_summary: contains generic phrase ({phrase!r}); name the "
                "exact tests, smoke checks, or missing proof for THIS repo."
            )

    impl = data.get("implementation_classification")
    if not isinstance(impl, list) or not impl:
        errors.append("implementation_classification: must be a non-empty list")
    else:
        for index, piece in enumerate(impl):
            errors.extend(validate_implementation_piece(piece, index))

    for field in ("remote_progress_check", "archive_dedup_check"):
        value = data.get(field, "")
        if not _is_nonempty_str(value):
            errors.append(f"{field}: must be a non-empty string")
            continue
        if not re.search(r"\d", value):
            errors.append(
                f"{field}: must reference concrete numbers (count of items reviewed); "
                "a bare 'no overlap' is insufficient."
            )

    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        errors.append("candidates: must be a list (may be empty)")
        candidates = []
    else:
        for index, candidate in enumerate(candidates):
            errors.extend(validate_candidate(candidate, index))

    deeper = data.get("deeper_review_needed")
    if not isinstance(deeper, bool):
        errors.append("deeper_review_needed: must be a boolean")
        deeper = False

    if deeper and not _is_nonempty_str(data.get("deeper_review_reason")):
        errors.append("deeper_review_reason: required when deeper_review_needed is true")

    if (
        not deeper
        and not candidates
        and not _is_nonempty_str(data.get("no_new_work_justification"))
    ):
        errors.append(
            "no_new_work_justification: required when candidates is empty and "
            "deeper_review_needed is false."
        )

    return errors


def validate_findings_file(path: Path, *, expected_repo: str | None = None) -> list[str]:
    """Convenience wrapper: read a findings.json and validate it."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"findings file: cannot read {path}: {exc}"]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [f"findings file: invalid JSON in {path}: {exc}"]
    return validate_findings(data, expected_repo=expected_repo)


def main() -> int:
    """CLI entrypoint: validate one or more findings.json files."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Paths to findings.json files to validate.")
    parser.add_argument(
        "--expected-repo", default=None, help="Optional expected repo (owner/name)."
    )
    args = parser.parse_args()

    overall_errors = 0
    for raw_path in args.paths:
        path = Path(raw_path)
        errors = validate_findings_file(path, expected_repo=args.expected_repo)
        if errors:
            overall_errors += len(errors)
            print(f"{path}: {len(errors)} error(s):")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"{path}: OK")
    return 1 if overall_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
