"""Tests for scripts/repo_review_queue_builder.py."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.repo_review_queue_builder import build_queue
from scripts.repo_review_scorecard import SCHEMA


def _write_converged(round2_dir: Path, repo: str, title: str) -> None:
    safe = repo.replace("/", "__")
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
    path.write_text(
        json.dumps(
            {
                "converged_candidates": [
                    {
                        "title": title,
                        "body": body,
                        "priority": "normal",
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )


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
