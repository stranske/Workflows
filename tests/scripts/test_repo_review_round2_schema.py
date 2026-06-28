from __future__ import annotations

import pytest
from scripts import repo_review_round2_schema as schema

LONG_REASON = "This reason is long enough to satisfy the schema validator minimum length."


def _valid_mark(**overrides: object) -> dict[str, object]:
    mark: dict[str, object] = {
        "source_agent": "codex",
        "candidate_index": 1,
        "mark": "agree-keep",
        "reason": LONG_REASON,
    }
    mark.update(overrides)
    return mark


def _valid_meta_candidate(**overrides: object) -> dict[str, object]:
    meta: dict[str, object] = {
        "proposed": True,
        "pattern": "Repeated stale repo-review guardrails",
        "title": "Audit stale repo-review guardrails across the codebase",
        "rationale": "Multiple concrete findings point at the same audit class.",
        "supporting_candidate_indexes": [
            {"agent": "codex", "candidate_index": 1},
            {"agent": "claude", "candidate_index": 2},
        ],
        "scope": "audit",
        "tasks": [
            "Enumerate every matching guardrail with file references.",
            "Classify each instance by risk and owner.",
            "File per-instance follow-up issues for fixes.",
        ],
        "acceptance_criteria": [
            "An audit report artifact lists every reviewed instance.",
            "Per-instance follow-up issues are filed for concrete fixes.",
            "The report records any intentionally deferred cases.",
        ],
        "non_goals": [
            "Do not bundle per-instance fixes into a single PR.",
        ],
        "priority": "normal",
        "confidence": "medium",
    }
    meta.update(overrides)
    return meta


def _valid_turn_output(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "agent": "codex",
        "repo": "stranske/Workflows",
        "turn": 1,
        "marks": [_valid_mark()],
        "own_candidates_revisions": [],
        "meta_candidate_proposal": {"proposed": False},
    }
    payload.update(overrides)
    return payload


def _valid_converged_set(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "v1",
        "repo": "stranske/Workflows",
        "turns_completed": 2,
        "round1_sources": [{"agent": "codex", "path": "/tmp/codex.json", "candidate_count": 1}],
        "converged_candidates": [
            {
                "title": "Add focused repo-review tests",
                "scope": "fix",
            }
        ],
        "deadlocked_candidates": [],
        "dropped_candidates": [],
        "meta_candidate": {"title": "Audit related repo-review gaps", "scope": "audit"},
        "negotiation_log": ["/tmp/round2/turn-1/codex.json"],
    }
    payload.update(overrides)
    return payload


def _assert_error(errors: list[str], substring: str) -> None:
    assert any(substring in error for error in errors), errors


@pytest.mark.parametrize("agent", ["codex", "claude", "pilot-testgen"])
def test_validate_mark_accepts_allowed_agents(agent: str) -> None:
    assert schema.validate_mark(_valid_mark(source_agent=agent), 0) == []


def test_validate_mark_rejects_unknown_agent() -> None:
    errors = schema.validate_mark(_valid_mark(source_agent="gemini"), 0)

    _assert_error(errors, "marks[0].source_agent: must be one of")


@pytest.mark.parametrize(
    ("mark_value", "missing_field", "expected_error"),
    [
        ("agree-merge", "merge_proposal", "marks[0].merge_proposal: required"),
        ("disagree-revise", "revision_proposal", "marks[0].revision_proposal: required"),
    ],
)
def test_validate_mark_requires_proposals_for_merge_and_revision(
    mark_value: str,
    missing_field: str,
    expected_error: str,
) -> None:
    errors = schema.validate_mark(_valid_mark(mark=mark_value), 0)

    assert missing_field not in _valid_mark(mark=mark_value)
    _assert_error(errors, expected_error)


def test_validate_mark_rejects_short_reason() -> None:
    errors = schema.validate_mark(_valid_mark(reason="Too short."), 0)

    _assert_error(errors, "marks[0].reason: must be \u226530 chars")


def test_validate_mark_disagree_drop_requires_citation() -> None:
    bare_prose = "This looks redundant based on general reviewer judgment but cites no evidence."
    errors = schema.validate_mark(_valid_mark(mark="disagree-drop", reason=bare_prose), 0)

    _assert_error(errors, "'disagree-drop' must cite a file ref")


@pytest.mark.parametrize(
    "reason",
    [
        "Drop because scripts/repo_review_round2_schema.py already covers it.",
        "Drop because tests/scripts/test_existing.py already exercises the case.",
        "Drop because #2621 already tracks the remaining follow-up.",
        "Drop because the merged PR already shipped the same validation.",
    ],
)
def test_validate_mark_disagree_drop_accepts_concrete_citations(reason: str) -> None:
    assert schema.validate_mark(_valid_mark(mark="disagree-drop", reason=reason), 0) == []


def test_validate_meta_candidate_proposed_false_has_no_extra_requirements() -> None:
    assert schema.validate_meta_candidate({"proposed": False}) == []


def test_validate_meta_candidate_requires_proposed_boolean() -> None:
    errors = schema.validate_meta_candidate({"pattern": "Missing proposed flag"})

    _assert_error(errors, "meta_candidate_proposal.proposed: must be a boolean")


def test_validate_meta_candidate_enforces_audit_scope() -> None:
    errors = schema.validate_meta_candidate(_valid_meta_candidate(scope="fix"))

    _assert_error(errors, "meta_candidate_proposal.scope: must be exactly 'audit'")


def test_validate_meta_candidate_requires_two_supporting_candidates() -> None:
    errors = schema.validate_meta_candidate(
        _valid_meta_candidate(
            supporting_candidate_indexes=[
                {"agent": "codex", "candidate_index": 1},
            ],
        )
    )

    _assert_error(errors, "supporting_candidate_indexes: must list \u22652 anchoring candidates")


def test_validate_meta_candidate_acceptance_must_reference_audit_or_report_token() -> None:
    errors = schema.validate_meta_candidate(
        _valid_meta_candidate(
            acceptance_criteria=[
                "Every reviewed instance has a clear owner.",
                "Every reviewed instance has an explicit risk class.",
                "Every reviewed instance has a concrete disposition.",
            ],
        )
    )

    _assert_error(errors, "acceptance_criteria: at least one criterion must reference")


def test_validate_meta_candidate_non_goals_must_forbid_bundling() -> None:
    errors = schema.validate_meta_candidate(
        _valid_meta_candidate(non_goals=["Do not change unrelated CI workflows."])
    )

    _assert_error(errors, "non_goals: must explicitly forbid bundling")


def test_validate_meta_candidate_high_confidence_requires_four_supports() -> None:
    errors = schema.validate_meta_candidate(_valid_meta_candidate(confidence="high"))

    _assert_error(errors, "confidence: 'high' requires \u22654 supporting")


def test_validate_meta_candidate_valid_payload_passes() -> None:
    assert schema.validate_meta_candidate(_valid_meta_candidate()) == []


def test_validate_turn_output_rejects_expected_repo_mismatch() -> None:
    errors = schema.validate_turn_output(
        _valid_turn_output(repo="stranske/Other"),
        expected_repo="stranske/Workflows",
    )

    _assert_error(errors, "repo: expected 'stranske/Workflows' got 'stranske/Other'")


def test_validate_turn_output_rejects_empty_marks() -> None:
    errors = schema.validate_turn_output(_valid_turn_output(marks=[]))

    _assert_error(errors, "marks: must be non-empty")


def test_validate_turn_output_rejects_invalid_turn() -> None:
    errors = schema.validate_turn_output(_valid_turn_output(turn=4))

    _assert_error(errors, "turn: must be 1, 2, or 3")


def test_validate_turn_output_accepts_valid_payload() -> None:
    assert schema.validate_turn_output(_valid_turn_output()) == []


def test_validate_converged_set_rejects_expected_repo_mismatch() -> None:
    errors = schema.validate_converged_set(
        _valid_converged_set(repo="stranske/Other"),
        expected_repo="stranske/Workflows",
    )

    _assert_error(errors, "repo: expected 'stranske/Workflows' got 'stranske/Other'")


def test_validate_converged_set_rejects_invalid_candidate_scope() -> None:
    errors = schema.validate_converged_set(
        _valid_converged_set(converged_candidates=[{"title": "Bad scope", "scope": "cleanup"}])
    )

    _assert_error(errors, "converged_candidates[0].scope: must be one of")


def test_validate_converged_set_rejects_non_object_meta_candidate() -> None:
    errors = schema.validate_converged_set(_valid_converged_set(meta_candidate="audit"))

    _assert_error(errors, "meta_candidate: must be null or an object")


def test_validate_converged_set_accepts_compact_payload_with_meta_candidate() -> None:
    assert schema.validate_converged_set(_valid_converged_set()) == []
