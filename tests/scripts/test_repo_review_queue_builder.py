"""Tests for scripts/repo_review_queue_builder.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from scripts import repo_review_queue_builder as queue_builder
from scripts.repo_review_queue_builder import (
    build_queue,
    is_uploadable_body,
    labels_for,
)
from scripts.repo_review_scorecard import SCHEMA


def _write_converged(
    round2_dir: Path,
    repo: str,
    title: str,
    body: str | None = None,
    priority: str = "normal",
    meta_candidate: dict[str, object] | None = None,
) -> None:
    safe = repo.replace("/", "__")
    if body is None:
        body = """## Why

Travel-Plan-Permission needs CI to execute the LangGraph path so orchestration coverage cannot pass by skipping the graph.

## Scope

- Install the orchestration extra in one deterministic CI/test path.
- Execute `run_policy_graph(..., prefer_langgraph=True)` against a small fixture plan.

## Non-Goals

- Do not expand every graph failure branch.
- Do not require live external services.

## Tasks

- [ ] Inspect `tests/python/test_langgraph_ci_gate.py` and `src/travel_plan_permission/orchestration/graph.py`.
- [ ] Add or update a pytest that imports LangGraph and runs `prefer_langgraph=True`.
- [ ] Update the repo-local CI command so the orchestration extra is installed for this test path.
- [ ] Document the exact local or CI command that proves LangGraph coverage.

## Acceptance Criteria

- [ ] The LangGraph-path test is not always skipped in the documented CI/test path.
- [ ] A broken graph compile or invocation causes a deterministic test failure.
- [ ] The PR notes the exact command or CI job used to prove the path.

## Implementation Notes

Relevant files: `pyproject.toml`, `.github/workflows/ci.yml`, `src/travel_plan_permission/orchestration/graph.py`, `tests/python/test_langgraph_ci_gate.py`.
"""
    path = round2_dir / safe / "converged.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, object] = {
        "converged_candidates": [
            {
                "title": title,
                "body": body,
                "priority": priority,
            }
        ]
    }
    if meta_candidate:
        data["meta_candidate"] = meta_candidate
    path.write_text(
        json.dumps(data) + "\n",
        encoding="utf-8",
    )


def _valid_body() -> str:
    """Return a minimal valid body that passes is_uploadable_body checks."""
    return "## Why\n\nReason.\n\n## Tasks\n\n- [ ] Task one"


def _sample_scorecard_scan() -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "generated_on": "2026-06-14T12:00:00Z",
        "config_source": "config/source_of_truth_docs.yml",
        "total_findings": 1,
        "total_errors": 0,
        "by_repo": [
            {
                "repo": "stranske/Workflows",
                "local_path": "Workflows-steward",
                "workflow": ".github/workflows/health-53-scorecard.yml",
                "source": {
                    "kind": "public_api",
                    "url": "https://api.securityscorecards.dev/projects/github.com/stranske/Workflows",
                },
                "minimum_score": 7.0,
                "findings": [
                    {
                        "finding_id": "scorecard:Branch-Protection",
                        "check": "Branch-Protection",
                        "score": 0.0,
                        "minimum_score": 7.0,
                        "priority": "high",
                        "reason": "branch protection not enabled on default branch",
                        "details": [],
                        "documentation_url": "https://example.com/branch-protection",
                        "source_url": "https://api.securityscorecards.dev/projects/github.com/stranske/Workflows",
                    }
                ],
                "skipped_findings": [],
                "errors": [],
            }
        ],
    }


def test_build_queue_includes_approved_scorecard_items(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    round2_dir = output_dir / "round2"
    output_dir.mkdir(parents=True)
    round2_dir.mkdir(parents=True)
    repo = "stranske/Travel-Plan-Permission"
    _write_converged(round2_dir, repo, "Keep approved repo-local work")

    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps(
            {
                "decisions": {
                    repo: {
                        "decision": "approve",
                        "approved_candidates": "all",
                    },
                    "stranske/Workflows": {
                        "decision": "defer",
                        "scorecard": {
                            "decision": "approve",
                            "approved_findings": ["scorecard:Branch-Protection"],
                            "dropped_findings": [],
                            "priority": "normal",
                            "priority_overrides": {},
                        },
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "scorecard-scan.json").write_text(
        json.dumps(_sample_scorecard_scan()) + "\n",
        encoding="utf-8",
    )

    result = build_queue(round2_dir, feedback_path)

    repos = {item["repo"] for item in result["issues"]}
    assert "stranske/Travel-Plan-Permission" in repos
    assert "stranske/Workflows" in repos
    scorecard_items = [
        item for item in result["issues"] if item.get("source_type") == "scorecard finding"
    ]
    assert len(scorecard_items) == 1
    assert scorecard_items[0]["scorecard_finding_id"] == "scorecard:Branch-Protection"


def test_build_queue_skips_unapproved_scorecard_findings(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    round2_dir = output_dir / "round2"
    output_dir.mkdir(parents=True)
    round2_dir.mkdir(parents=True)
    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps(
            {
                "decisions": {
                    "stranske/Workflows": {
                        "decision": "defer",
                        "scorecard": {
                            "decision": "defer",
                            "approved_findings": [],
                            "dropped_findings": [],
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "scorecard-scan.json").write_text(
        json.dumps(_sample_scorecard_scan()) + "\n",
        encoding="utf-8",
    )

    result = build_queue(round2_dir, feedback_path)

    assert result["issues"] == []
    assert any("scorecard" in skipped["reason"] for skipped in result["skipped"])


# =============================================================================
# Priority normalization tests for labels_for()
# =============================================================================


def test_labels_for_normal_priority() -> None:
    c = {"priority": "normal"}
    labels = labels_for(c, is_meta=False)
    assert labels == ["repo-review-approved", "priority:normal"]


def test_labels_for_high_priority() -> None:
    c = {"priority": "high"}
    labels = labels_for(c, is_meta=False)
    assert labels == ["repo-review-approved", "priority:high"]


def test_labels_for_low_priority() -> None:
    c = {"priority": "low"}
    labels = labels_for(c, is_meta=False)
    assert labels == ["repo-review-approved", "priority:low"]


def test_labels_for_unexpected_priority_normalizes_to_normal() -> None:
    c = {"priority": "critical"}
    labels = labels_for(c, is_meta=False)
    assert labels == ["repo-review-approved", "priority:normal"]


def test_labels_for_empty_priority_normalizes_to_normal() -> None:
    c = {}
    labels = labels_for(c, is_meta=False)
    assert labels == ["repo-review-approved", "priority:normal"]


def test_labels_for_meta_candidate() -> None:
    c = {"priority": "high"}
    labels = labels_for(c, is_meta=True)
    assert labels == ["repo-review-approved", "priority:high", "repo-review-meta-audit"]


# =============================================================================
# is_uploadable_body tests
# =============================================================================


def test_is_uploadable_body_valid() -> None:
    ok, why = is_uploadable_body("## Why\n\nReason.\n\n## Tasks\n\n- [ ] Task")
    assert ok is True
    assert why == ""


def test_is_uploadable_body_empty() -> None:
    ok, why = is_uploadable_body(None)
    assert ok is False
    assert why == "empty body"


def test_is_uploadable_body_empty_string() -> None:
    ok, why = is_uploadable_body("")
    assert ok is False
    assert why == "empty body"


def test_is_uploadable_body_insufficient_evidence() -> None:
    ok, why = is_uploadable_body("INSUFFICIENT_EVIDENCE: need more info")
    assert ok is False
    assert why == "INSUFFICIENT_EVIDENCE marker"


def test_is_uploadable_body_missing_why() -> None:
    ok, why = is_uploadable_body("## Tasks\n\n- [ ] Task")
    assert ok is False
    assert why == "missing required sections"


def test_is_uploadable_body_missing_tasks() -> None:
    ok, why = is_uploadable_body("## Why\n\nReason.")
    assert ok is False
    assert why == "missing required sections"


def test_build_queue_records_missing_and_invalid_converged_inputs(tmp_path: Path) -> None:
    """Approved decisions do not turn absent or malformed input into issues."""
    round2_dir = tmp_path / "round2"
    round2_dir.mkdir()
    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps(
            {
                "decisions": {
                    "org/Missing": {"decision": "approve"},
                    "org/NoFile": {"decision": "approve"},
                    "org/Broken": {"decision": "approve"},
                }
            }
        ),
        encoding="utf-8",
    )
    (round2_dir / "org__NoFile").mkdir()
    broken = round2_dir / "org__Broken"
    broken.mkdir()
    (broken / "converged.json").write_text("{not json", encoding="utf-8")

    result = build_queue(round2_dir, feedback_path, {"issues": [], "pending": [], "dropped": []})

    assert result["issues"] == []
    reasons = {item["repo"]: item["reason"] for item in result["skipped"]}
    assert reasons["org/Missing"] == "no converged.json directory"
    assert reasons["org/NoFile"] == "converged.json missing"
    assert reasons["org/Broken"].startswith("converged.json parse error:")


def test_build_queue_skips_invalid_scorecard_issue_and_records_pending_and_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    round2_dir = tmp_path / "round2"
    round2_dir.mkdir()
    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text('{"decisions": {}}', encoding="utf-8")
    scorecard = {
        "issues": [{"repo": "org/Bad", "body_valid": True, "body_quality_errors": ["bad"]}],
        "pending": [{"repo": "org/Pending", "finding_id": "p", "reason": "awaiting proof"}],
        "dropped": [{"repo": "org/Dropped", "finding_id": "d"}],
    }
    monkeypatch.setattr(queue_builder, "approved_scorecard_issue_items", lambda *_args: scorecard)

    result = build_queue(round2_dir, feedback_path, scorecard)

    assert result["issues"] == []
    assert {entry["repo"]: entry["reason"] for entry in result["skipped"]} == {
        "org/Bad": "scorecard issue body failed quality gate",
        "org/Pending": "awaiting proof",
        "org/Dropped": "scorecard finding dropped",
    }


# =============================================================================
# Decision routing tests for build_queue
# =============================================================================


def test_decision_approve_includes_candidate(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    round2_dir = output_dir / "round2"
    output_dir.mkdir(parents=True)
    round2_dir.mkdir(parents=True)
    repo = "stranske/Test-Repo"
    _write_converged(round2_dir, repo, "Test issue", body=_valid_body())

    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps({"decisions": {repo: {"decision": "approve"}}}),
        encoding="utf-8",
    )
    (output_dir / "scorecard-scan.json").write_text(
        json.dumps({"schema": SCHEMA, "by_repo": []}) + "\n",
        encoding="utf-8",
    )

    result = build_queue(round2_dir, feedback_path)

    assert len(result["issues"]) == 1
    assert result["issues"][0]["repo"] == repo
    assert result["issues"][0]["title"] == "Test issue"
    assert result["skipped"] == []


def test_decision_revise_includes_candidate(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    round2_dir = output_dir / "round2"
    output_dir.mkdir(parents=True)
    round2_dir.mkdir(parents=True)
    repo = "stranske/Test-Repo"
    _write_converged(round2_dir, repo, "Test issue", body=_valid_body())

    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps({"decisions": {repo: {"decision": "revise"}}}),
        encoding="utf-8",
    )
    (output_dir / "scorecard-scan.json").write_text(
        json.dumps({"schema": SCHEMA, "by_repo": []}) + "\n",
        encoding="utf-8",
    )

    result = build_queue(round2_dir, feedback_path)

    assert len(result["issues"]) == 1
    assert result["issues"][0]["repo"] == repo


def test_decision_defer_skips_repo(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    round2_dir = output_dir / "round2"
    output_dir.mkdir(parents=True)
    round2_dir.mkdir(parents=True)
    repo = "stranske/Test-Repo"
    _write_converged(round2_dir, repo, "Test issue", body=_valid_body())

    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps({"decisions": {repo: {"decision": "defer"}}}),
        encoding="utf-8",
    )
    (output_dir / "scorecard-scan.json").write_text(
        json.dumps({"schema": SCHEMA, "by_repo": []}) + "\n",
        encoding="utf-8",
    )

    result = build_queue(round2_dir, feedback_path)

    assert result["issues"] == []
    assert any(
        skipped["repo"] == repo and skipped["reason"] == "decision=defer"
        for skipped in result["skipped"]
    )


def test_decision_no_new_work_accept_skips_repo(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    round2_dir = output_dir / "round2"
    output_dir.mkdir(parents=True)
    round2_dir.mkdir(parents=True)
    repo = "stranske/Test-Repo"
    _write_converged(round2_dir, repo, "Test issue", body=_valid_body())

    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps({"decisions": {repo: {"decision": "no_new_work_accept"}}}),
        encoding="utf-8",
    )
    (output_dir / "scorecard-scan.json").write_text(
        json.dumps({"schema": SCHEMA, "by_repo": []}) + "\n",
        encoding="utf-8",
    )

    result = build_queue(round2_dir, feedback_path)

    assert result["issues"] == []
    assert any(
        skipped["repo"] == repo and skipped["reason"] == "decision=no_new_work_accept"
        for skipped in result["skipped"]
    )


def test_decision_unhandled_skips_repo(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    round2_dir = output_dir / "round2"
    output_dir.mkdir(parents=True)
    round2_dir.mkdir(parents=True)
    repo = "stranske/Test-Repo"
    _write_converged(round2_dir, repo, "Test issue", body=_valid_body())

    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps({"decisions": {repo: {"decision": "unknown_decision"}}}),
        encoding="utf-8",
    )
    (output_dir / "scorecard-scan.json").write_text(
        json.dumps({"schema": SCHEMA, "by_repo": []}) + "\n",
        encoding="utf-8",
    )

    result = build_queue(round2_dir, feedback_path)

    assert result["issues"] == []
    assert any(
        skipped["repo"] == repo and skipped["reason"] == "unhandled decision=unknown_decision"
        for skipped in result["skipped"]
    )


def test_decision_compound_revise_pipe_approve(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    round2_dir = output_dir / "round2"
    output_dir.mkdir(parents=True)
    round2_dir.mkdir(parents=True)
    repo = "stranske/Test-Repo"
    _write_converged(round2_dir, repo, "Test issue", body=_valid_body())

    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps({"decisions": {repo: {"decision": "revise|deeper-review"}}}),
        encoding="utf-8",
    )
    (output_dir / "scorecard-scan.json").write_text(
        json.dumps({"schema": SCHEMA, "by_repo": []}) + "\n",
        encoding="utf-8",
    )

    result = build_queue(round2_dir, feedback_path)

    assert len(result["issues"]) == 1
    assert result["issues"][0]["repo"] == repo


# =============================================================================
# Candidate skip tests (empty body, INSUFFICIENT_EVIDENCE)
# =============================================================================


def test_empty_body_candidate_skipped(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    round2_dir = output_dir / "round2"
    output_dir.mkdir(parents=True)
    round2_dir.mkdir(parents=True)
    repo = "stranske/Test-Repo"
    safe = repo.replace("/", "__")
    path = round2_dir / safe / "converged.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"converged_candidates": [{"title": "Test issue", "body": None, "priority": "normal"}]}
        )
        + "\n",
        encoding="utf-8",
    )

    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps({"decisions": {repo: {"decision": "approve"}}}),
        encoding="utf-8",
    )
    (output_dir / "scorecard-scan.json").write_text(
        json.dumps({"schema": SCHEMA, "by_repo": []}) + "\n",
        encoding="utf-8",
    )

    result = build_queue(round2_dir, feedback_path)

    assert result["issues"] == []
    assert any(
        skipped["repo"] == repo
        and skipped["reason"] == "empty body"
        and skipped.get("candidate_index") == "0"
        for skipped in result["skipped"]
    )


def test_insufficient_evidence_candidate_skipped(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    round2_dir = output_dir / "round2"
    output_dir.mkdir(parents=True)
    round2_dir.mkdir(parents=True)
    repo = "stranske/Test-Repo"
    _write_converged(round2_dir, repo, "Test issue", body="INSUFFICIENT_EVIDENCE: need more data")

    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps({"decisions": {repo: {"decision": "approve"}}}),
        encoding="utf-8",
    )
    (output_dir / "scorecard-scan.json").write_text(
        json.dumps({"schema": SCHEMA, "by_repo": []}) + "\n",
        encoding="utf-8",
    )

    result = build_queue(round2_dir, feedback_path)

    assert result["issues"] == []
    assert any(
        skipped["repo"] == repo
        and skipped["reason"] == "INSUFFICIENT_EVIDENCE marker"
        and skipped.get("candidate_index") == "0"
        for skipped in result["skipped"]
    )


def test_mixed_valid_and_invalid_candidates(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    round2_dir = output_dir / "round2"
    output_dir.mkdir(parents=True)
    round2_dir.mkdir(parents=True)
    repo = "stranske/Test-Repo"

    safe = repo.replace("/", "__")
    path = round2_dir / safe / "converged.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "converged_candidates": [
                    {"title": "Valid issue", "body": _valid_body(), "priority": "normal"},
                    {"title": "Empty body", "body": None, "priority": "normal"},
                    {
                        "title": "Insufficient",
                        "body": "INSUFFICIENT_EVIDENCE: stub",
                        "priority": "normal",
                    },
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps({"decisions": {repo: {"decision": "approve"}}}),
        encoding="utf-8",
    )
    (output_dir / "scorecard-scan.json").write_text(
        json.dumps({"schema": SCHEMA, "by_repo": []}) + "\n",
        encoding="utf-8",
    )

    result = build_queue(round2_dir, feedback_path)

    assert len(result["issues"]) == 1
    assert result["issues"][0]["title"] == "Valid issue"
    skipped_reasons = {skipped["reason"] for skipped in result["skipped"]}
    assert "empty body" in skipped_reasons
    assert "INSUFFICIENT_EVIDENCE marker" in skipped_reasons


# =============================================================================
# Meta candidate tests (include_meta_candidate)
# =============================================================================


def test_include_meta_candidate_valid(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    round2_dir = output_dir / "round2"
    output_dir.mkdir(parents=True)
    round2_dir.mkdir(parents=True)
    repo = "stranske/Test-Repo"
    meta = {"title": "Meta audit", "body": _valid_body(), "priority": "high"}
    _write_converged(round2_dir, repo, "Test issue", body=_valid_body(), meta_candidate=meta)

    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps({"decisions": {repo: {"decision": "approve", "include_meta_candidate": True}}}),
        encoding="utf-8",
    )
    (output_dir / "scorecard-scan.json").write_text(
        json.dumps({"schema": SCHEMA, "by_repo": []}) + "\n",
        encoding="utf-8",
    )

    result = build_queue(round2_dir, feedback_path)

    issue_titles = {item["title"] for item in result["issues"]}
    assert "Test issue" in issue_titles
    assert "Meta audit" in issue_titles
    meta_issue = next(item for item in result["issues"] if item["title"] == "Meta audit")
    assert "repo-review-meta-audit" in meta_issue["labels"]


def test_include_meta_candidate_invalid_body_skipped(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    round2_dir = output_dir / "round2"
    output_dir.mkdir(parents=True)
    round2_dir.mkdir(parents=True)
    repo = "stranske/Test-Repo"
    meta = {"title": "Meta audit", "body": None, "priority": "high"}
    _write_converged(round2_dir, repo, "Test issue", body=_valid_body(), meta_candidate=meta)

    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps({"decisions": {repo: {"decision": "approve", "include_meta_candidate": True}}}),
        encoding="utf-8",
    )
    (output_dir / "scorecard-scan.json").write_text(
        json.dumps({"schema": SCHEMA, "by_repo": []}) + "\n",
        encoding="utf-8",
    )

    result = build_queue(round2_dir, feedback_path)

    issue_titles = {item["title"] for item in result["issues"]}
    assert "Test issue" in issue_titles
    assert "Meta audit" not in issue_titles
    assert any(
        skipped["repo"] == repo
        and skipped.get("candidate_index") == "meta"
        and skipped["reason"] == "empty body"
        for skipped in result["skipped"]
    )


def test_include_meta_candidate_false_excludes_meta(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    round2_dir = output_dir / "round2"
    output_dir.mkdir(parents=True)
    round2_dir.mkdir(parents=True)
    repo = "stranske/Test-Repo"
    meta = {"title": "Meta audit", "body": _valid_body(), "priority": "high"}
    _write_converged(round2_dir, repo, "Test issue", body=_valid_body(), meta_candidate=meta)

    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps({"decisions": {repo: {"decision": "approve", "include_meta_candidate": False}}}),
        encoding="utf-8",
    )
    (output_dir / "scorecard-scan.json").write_text(
        json.dumps({"schema": SCHEMA, "by_repo": []}) + "\n",
        encoding="utf-8",
    )

    result = build_queue(round2_dir, feedback_path)

    issue_titles = {item["title"] for item in result["issues"]}
    assert "Test issue" in issue_titles
    assert "Meta audit" not in issue_titles


def test_include_meta_candidate_not_specified_excludes_meta(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    round2_dir = output_dir / "round2"
    output_dir.mkdir(parents=True)
    round2_dir.mkdir(parents=True)
    repo = "stranske/Test-Repo"
    meta = {"title": "Meta audit", "body": _valid_body(), "priority": "high"}
    _write_converged(round2_dir, repo, "Test issue", body=_valid_body(), meta_candidate=meta)

    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps({"decisions": {repo: {"decision": "approve"}}}),
        encoding="utf-8",
    )
    (output_dir / "scorecard-scan.json").write_text(
        json.dumps({"schema": SCHEMA, "by_repo": []}) + "\n",
        encoding="utf-8",
    )

    result = build_queue(round2_dir, feedback_path)

    issue_titles = {item["title"] for item in result["issues"]}
    assert "Test issue" in issue_titles
    assert "Meta audit" not in issue_titles


def test_build_queue_reports_missing_directory_and_invalid_converged_json(tmp_path: Path) -> None:
    feedback = tmp_path / "feedback.json"
    feedback.write_text(json.dumps({"decisions": {"owner/repo": {"decision": "approve"}}}))
    with pytest.raises(FileNotFoundError, match="round2 dir not found"):
        build_queue(tmp_path / "missing", feedback, {"by_repo": []})

    round2 = tmp_path / "round2"
    path = round2 / "owner__repo" / "converged.json"
    path.parent.mkdir(parents=True)
    path.write_text("not json")
    result = build_queue(round2, feedback, {"issues": [], "pending": [], "dropped": []})
    assert result["issues"] == []
    assert "parse error" in result["skipped"][0]["reason"]


def test_main_writes_queue_and_prints_per_repo(tmp_path: Path, monkeypatch, capsys) -> None:
    round2 = tmp_path / "round2"
    _write_converged(round2, "owner/repo", "Queued", body=_valid_body())
    feedback = tmp_path / "feedback.json"
    feedback.write_text(json.dumps({"decisions": {"owner/repo": {"decision": "approve"}}}))
    scorecard = tmp_path / "scorecard.json"
    scorecard.write_text(json.dumps({"schema": SCHEMA, "by_repo": []}))
    output = tmp_path / "out" / "queue.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "queue-builder",
            "--round2-dir",
            str(round2),
            "--feedback",
            str(feedback),
            "--scorecard-scan",
            str(scorecard),
            "--out",
            str(output),
        ],
    )
    assert queue_builder.main() == 0
    assert json.loads(output.read_text())["issues"][0]["title"] == "Queued"
    assert "owner/repo: 1" in capsys.readouterr().out


def test_main_reports_missing_round2_directory(tmp_path: Path, monkeypatch, capsys) -> None:
    feedback = tmp_path / "feedback.json"
    feedback.write_text(json.dumps({"decisions": {}}))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "queue-builder",
            "--round2-dir",
            str(tmp_path / "missing"),
            "--feedback",
            str(feedback),
            "--out",
            str(tmp_path / "queue.json"),
        ],
    )
    assert queue_builder.main() == 2
    assert "round2 dir not found" in capsys.readouterr().err


def test_include_meta_candidate_true_with_missing_meta_is_skipped(tmp_path: Path) -> None:
    output_dir = tmp_path / "repo-review"
    round2_dir = output_dir / "round2"
    output_dir.mkdir(parents=True)
    round2_dir.mkdir(parents=True)
    repo = "stranske/Test-Repo"
    _write_converged(round2_dir, repo, "Test issue", body=_valid_body(), meta_candidate=None)
    # Force meta_candidate absent even if helper wrote null
    converged = round2_dir / "stranske__Test-Repo" / "converged.json"
    data = json.loads(converged.read_text(encoding="utf-8"))
    data.pop("meta_candidate", None)
    converged.write_text(json.dumps(data), encoding="utf-8")

    feedback_path = tmp_path / "feedback.json"
    feedback_path.write_text(
        json.dumps({"decisions": {repo: {"decision": "approve", "include_meta_candidate": True}}}),
        encoding="utf-8",
    )
    (output_dir / "scorecard-scan.json").write_text(
        json.dumps({"schema": SCHEMA, "by_repo": []}) + "\n",
        encoding="utf-8",
    )

    result = build_queue(round2_dir, feedback_path)
    assert len(result["issues"]) == 1
    assert result["issues"][0]["title"] == "Test issue"


def test_main_quiet_suppresses_details_and_nonquiet_prints_skipped(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    round2 = tmp_path / "round2"
    _write_converged(round2, "owner/repo", "Queued", body=_valid_body())
    feedback = tmp_path / "feedback.json"
    feedback.write_text(
        json.dumps(
            {
                "decisions": {
                    "owner/repo": {"decision": "approve"},
                    "owner/skip": {"decision": "defer"},
                }
            }
        )
    )
    scorecard = tmp_path / "scorecard.json"
    scorecard.write_text(json.dumps({"schema": SCHEMA, "by_repo": []}))
    output = tmp_path / "out" / "queue.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "queue-builder",
            "--round2-dir",
            str(round2),
            "--feedback",
            str(feedback),
            "--scorecard-scan",
            str(scorecard),
            "--out",
            str(output),
            "--quiet",
        ],
    )
    assert queue_builder.main() == 0
    quiet_out = capsys.readouterr().out
    assert "owner/repo: 1" not in quiet_out
    assert "Skipped" not in quiet_out

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "queue-builder",
            "--round2-dir",
            str(round2),
            "--feedback",
            str(feedback),
            "--scorecard-scan",
            str(scorecard),
            "--out",
            str(tmp_path / "out" / "queue2.json"),
        ],
    )
    assert queue_builder.main() == 0
    loud_out = capsys.readouterr().out
    assert "owner/repo: 1" in loud_out
    assert "Skipped" in loud_out
    assert "decision=defer" in loud_out
