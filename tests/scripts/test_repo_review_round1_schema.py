from __future__ import annotations

import json
import sys

import pytest
from scripts import repo_review_round1_schema as schema

LONG_SUMMARY = (
    "This repo-review payload describes the Workflows automation contract, including "
    "the exact queue state, evidence paths, verifier expectations, and follow-up "
    "routing that the round-one reviewer observed in repository files."
)
LONG_FIELD = (
    "The candidate names a concrete repository behavior and cites the observed "
    "implementation state with enough context for a maintainer to act."
)


def _assert_error(errors: list[str], substring: str) -> None:
    assert any(substring in error for error in errors), errors


def _valid_implementation_piece(**overrides: object) -> dict[str, object]:
    piece: dict[str, object] = {
        "piece": "Round-one schema validator",
        "status": "implemented-and-verified",
        "evidence": ["scripts/repo_review_round1_schema.py:1"],
    }
    piece.update(overrides)
    return piece


def _valid_candidate(**overrides: object) -> dict[str, object]:
    candidate: dict[str, object] = {
        "title": "Add strict schema evidence validation",
        "gap": LONG_FIELD,
        "current_state": LONG_FIELD,
        "required_change": LONG_FIELD,
        "design_refs": ["docs/ops/REPO_REVIEW_ROUND1_SCHEMA.md#Evidence Rules"],
        "implementation_refs": ["scripts/repo_review_round1_schema.py:140-210"],
        "test_refs": ["tests/scripts/test_repo_review_round1_schema.py"],
        "acceptance_criteria": [
            "pytest covers valid and invalid candidate payloads.",
            "CI fails when repo-relative evidence refs are malformed.",
        ],
        "non_goals": ["Do not change repo-review prompts."],
        "tasks": [
            "Add in-memory payload coverage for candidate validation.",
            "Assert exact schema errors for malformed evidence refs.",
        ],
        "priority": "normal",
        "confidence": "medium",
    }
    candidate.update(overrides)
    return candidate


def _valid_findings(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "agent": "codex",
        "repo": "stranske/Workflows",
        "design_summary": LONG_SUMMARY,
        "readiness_summary": LONG_SUMMARY,
        "implementation_classification": [_valid_implementation_piece()],
        "remote_progress_check": "Reviewed 4 open pull requests before filing candidates.",
        "archive_dedup_check": "Compared 3 archived review artifacts for overlap.",
        "candidates": [_valid_candidate()],
        "deeper_review_needed": False,
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "value",
    [
        "scripts/repo_review_round1_schema.py",
        "scripts/repo_review_round1_schema.py:104",
        "scripts/repo_review_round1_schema.py:104-124",
        "AGENTS.md#Current Consumer Defaults",
    ],
)
def test_repo_relative_path_accepts_file_refs_line_ranges_and_spaced_anchors(
    value: str,
) -> None:
    assert schema._looks_like_repo_relative_path(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "https://github.com/stranske/Workflows/pull/2627",
        "the schema validator checks this behavior",
    ],
)
def test_repo_relative_path_rejects_empty_urls_and_prose(value: str) -> None:
    assert not schema._looks_like_repo_relative_path(value)


@pytest.mark.parametrize(
    "status",
    [
        "implemented-and-verified",
        "partial",
        "missing",
        "stale-or-conflicting",
    ],
)
def test_validate_implementation_piece_accepts_allowed_statuses(status: str) -> None:
    assert (
        schema.validate_implementation_piece(
            _valid_implementation_piece(status=status),
            0,
        )
        == []
    )


def test_validate_implementation_piece_requires_core_fields() -> None:
    errors = schema.validate_implementation_piece({}, 0)

    _assert_error(errors, "implementation_classification[0].piece: must be a non-empty string")
    _assert_error(errors, "implementation_classification[0].status: must be one of")
    _assert_error(errors, "implementation_classification[0].evidence: must be a non-empty list")


def test_validate_candidate_rejects_generic_gap_phrase() -> None:
    errors = schema.validate_candidate(
        _valid_candidate(
            gap="The implementation is incomplete and still needs repo-specific evidence."
        ),
        0,
    )

    _assert_error(errors, "candidates[0].gap: contains generic phrase")


def test_validate_candidate_rejects_invalid_repo_refs() -> None:
    errors = schema.validate_candidate(
        _valid_candidate(design_refs=["the design document explains this behavior"]),
        0,
    )

    _assert_error(errors, "candidates[0].design_refs[0]")
    _assert_error(errors, "does not look like a repo-relative file ref")


def test_validate_candidate_rejects_too_short_substance_fields() -> None:
    errors = schema.validate_candidate(
        _valid_candidate(current_state="Too short.", required_change="Also short."),
        0,
    )

    _assert_error(errors, "candidates[0].current_state: must be")
    _assert_error(errors, "candidates[0].required_change: must be")


def test_validate_candidate_requires_test_like_acceptance_criteria() -> None:
    errors = schema.validate_candidate(
        _valid_candidate(
            acceptance_criteria=[
                "Document the behavior for maintainers.",
                "Update the rollout notes for operators.",
            ],
        ),
        0,
    )

    _assert_error(errors, "candidates[0].acceptance_criteria: at least one criterion")


def test_validate_candidate_rejects_workflows_misroute_title_tokens() -> None:
    errors = schema.validate_candidate(
        _valid_candidate(title="Fix workflow sync behavior in generated repo prompts"),
        0,
    )

    _assert_error(errors, "candidates[0].title: looks like Workflows-maintenance work")


def test_validate_candidate_accepts_valid_candidate_payload() -> None:
    assert schema.validate_candidate(_valid_candidate(), 0) == []


def test_validate_findings_rejects_expected_repo_mismatch() -> None:
    errors = schema.validate_findings(
        _valid_findings(repo="stranske/Other"),
        expected_repo="stranske/Workflows",
    )

    _assert_error(errors, "repo: expected 'stranske/Workflows' but got 'stranske/Other'")


def test_validate_findings_accepts_pilot_agents() -> None:
    assert schema.validate_findings(_valid_findings(agent="pilot-testgen")) == []


def test_validate_findings_rejects_generic_summaries() -> None:
    generic_summary = (
        "This report says the repo is ready for normal coding-agent implementation "
        "without naming the concrete Workflows files, evidence counts, verifier "
        "state, or repository-specific behavior that the reviewer inspected."
    )
    errors = schema.validate_findings(
        _valid_findings(design_summary=generic_summary, readiness_summary=generic_summary)
    )

    _assert_error(errors, "design_summary: contains generic phrase")
    _assert_error(errors, "readiness_summary: contains generic phrase")


def test_validate_findings_accepts_valid_minimal_payload() -> None:
    assert schema.validate_findings(_valid_findings()) == []


@pytest.mark.parametrize(
    ("candidate", "message"),
    [
        (None, "must be an object"),
        (_valid_candidate(title=""), "title: must be a non-empty string"),
        (_valid_candidate(title="x" * 121), "title: must be ≤120 chars"),
        (_valid_candidate(gap=None), "gap: must be a non-empty string"),
        (_valid_candidate(design_refs=[]), "design_refs: must be a non-empty list"),
        (_valid_candidate(acceptance_criteria=["only one"]), "acceptance_criteria: must be a list"),
        (_valid_candidate(non_goals=[]), "non_goals: must be a non-empty list"),
        (_valid_candidate(tasks=["only one"]), "tasks: must be a list"),
        (_valid_candidate(priority="urgent"), "priority: must be one of"),
        (_valid_candidate(confidence="certain"), "confidence: must be one of"),
    ],
)
def test_validate_candidate_reports_each_required_field(candidate: object, message: str) -> None:
    _assert_error(schema.validate_candidate(candidate, 0), message)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (None, "findings: top-level must be an object"),
        (_valid_findings(agent="unknown"), "agent: must be one of"),
        (_valid_findings(repo="Workflows"), "repo: must be in 'owner/name' form"),
        (_valid_findings(design_summary=""), "design_summary: must be a non-empty string"),
        (_valid_findings(readiness_summary="short"), "readiness_summary: must be ≥"),
        (
            _valid_findings(implementation_classification=[]),
            "implementation_classification: must be",
        ),
        (
            _valid_findings(remote_progress_check="reviewed"),
            "remote_progress_check: must reference",
        ),
        (
            _valid_findings(archive_dedup_check=""),
            "archive_dedup_check: must be a non-empty string",
        ),
        (_valid_findings(candidates={}), "candidates: must be a list"),
        (_valid_findings(deeper_review_needed="false"), "deeper_review_needed: must be a boolean"),
        (
            _valid_findings(candidates=[], deeper_review_needed=False),
            "no_new_work_justification: required",
        ),
        (
            _valid_findings(deeper_review_needed=True, deeper_review_reason=""),
            "deeper_review_reason: required",
        ),
    ],
)
def test_validate_findings_reports_required_top_level_fields(payload: object, message: str) -> None:
    _assert_error(schema.validate_findings(payload), message)


def test_validate_findings_file_reports_unreadable_and_invalid_json(tmp_path) -> None:
    assert "cannot read" in schema.validate_findings_file(tmp_path / "missing.json")[0]
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert "invalid JSON" in schema.validate_findings_file(bad)[0]


def test_main_prints_per_file_results_and_returns_aggregate_failure(
    tmp_path, monkeypatch, capsys
) -> None:
    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps(_valid_findings()), encoding="utf-8")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["schema", str(valid), str(invalid), "--expected-repo", "stranske/Workflows"]
    )
    assert schema.main() == 1
    output = capsys.readouterr().out
    assert f"{valid}: OK" in output
    assert f"{invalid}: " in output
    assert "error(s)" in output
