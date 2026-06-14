"""Tests for scripts/repo_review_scorecard.py."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from scripts.repo_review_issue_quality import issue_body_quality_errors
from scripts.repo_review_notify import format_scorecard_section
from scripts.repo_review_scorecard import (
    SCHEMA,
    approved_scorecard_issue_items,
    build_scorecard_issue_body,
    filter_scorecard_findings,
    load_scorecard_config,
    load_scorecard_scan,
    parse_scorecard_api_response,
    scan_scorecard_repos,
)

FIXTURE_API = Path(__file__).parent / "fixtures" / "repo_review_scorecard" / "api_response.json"


def _sample_scan(*, repo: str = "stranske/Workflows") -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "generated_on": "2026-06-14T12:00:00Z",
        "config_source": "config/source_of_truth_docs.yml",
        "total_findings": 2,
        "total_errors": 0,
        "by_repo": [
            {
                "repo": repo,
                "local_path": "Workflows-steward",
                "workflow": ".github/workflows/health-53-scorecard.yml",
                "source": {
                    "kind": "public_api",
                    "url": f"https://api.securityscorecards.dev/projects/github.com/{repo}",
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
                        "details": ["Warn: no branch protection settings found"],
                        "documentation_url": "https://github.com/ossf/scorecard/blob/main/docs/checks.md#branch-protection",
                        "source_url": f"https://api.securityscorecards.dev/projects/github.com/{repo}",
                    },
                    {
                        "finding_id": "scorecard:Token-Permissions",
                        "check": "Token-Permissions",
                        "score": 4.0,
                        "minimum_score": 7.0,
                        "priority": "normal",
                        "reason": "detected workflow tokens with write permissions",
                        "details": ["Info: 'contents: write' in .github/workflows/example.yml"],
                        "documentation_url": "https://github.com/ossf/scorecard/blob/main/docs/checks.md#token-permissions",
                        "source_url": f"https://api.securityscorecards.dev/projects/github.com/{repo}",
                    },
                ],
                "skipped_findings": [],
                "errors": [],
            }
        ],
    }


def test_parse_scorecard_api_response_filters_only_checks_below_threshold() -> None:
    payload = json.loads(FIXTURE_API.read_text(encoding="utf-8"))
    parsed = parse_scorecard_api_response(payload)
    findings, _skipped = filter_scorecard_findings(
        parsed,
        minimum_score=7.0,
        include_checks=[],
        exclude_checks=[],
        max_findings_per_repo=5,
        source_url="https://api.securityscorecards.dev/projects/github.com/stranske/Workflows",
    )
    checks = {item["check"] for item in findings}
    assert checks == {"Branch-Protection", "Token-Permissions"}
    assert all(float(item["score"]) < 7.0 for item in findings)
    assert findings[0]["check"] == "Branch-Protection"
    assert findings[0]["priority"] == "high"
    assert findings[1]["priority"] == "normal"


def test_build_scorecard_issue_body_passes_issue_body_quality_errors() -> None:
    finding = {
        "finding_id": "scorecard:Branch-Protection",
        "check": "Branch-Protection",
        "score": 0.0,
        "minimum_score": 7.0,
        "reason": "branch protection not enabled on default branch",
        "documentation_url": "https://github.com/ossf/scorecard/blob/main/docs/checks.md#branch-protection",
    }
    body = build_scorecard_issue_body(
        repo="stranske/Workflows",
        finding=finding,
        workflow_path=".github/workflows/health-53-scorecard.yml",
    )
    assert issue_body_quality_errors(body) == []


def test_approved_scorecard_issue_items_requires_explicit_approved_findings() -> None:
    feedback = {
        "scorecard_defaults": {"decision": "defer", "approved_findings": []},
        "decisions": {
            "stranske/Workflows": {
                "decision": "defer",
                "approved_candidates": "all",
                "scorecard": {
                    "decision": "defer",
                    "approved_findings": [],
                    "dropped_findings": [],
                    "priority": "normal",
                    "priority_overrides": {},
                },
            }
        },
    }
    result = approved_scorecard_issue_items(_sample_scan(), feedback, "2026-06-14")
    assert result["issues"] == []
    assert len(result["pending"]) == 2
    assert all(
        "not explicitly approved" in item["reason"] or "decision=defer" in item["reason"]
        for item in result["pending"]
    )


def test_approved_scorecard_issue_items_rejects_approved_findings_all() -> None:
    feedback = {
        "scorecard_defaults": {"decision": "defer", "approved_findings": []},
        "decisions": {
            "stranske/Workflows": {
                "scorecard": {
                    "decision": "approve",
                    "approved_findings": "all",
                    "dropped_findings": [],
                    "priority": "normal",
                    "priority_overrides": {},
                }
            }
        },
    }
    result = approved_scorecard_issue_items(_sample_scan(), feedback, "2026-06-14")
    assert result["issues"] == []
    assert any(
        "approved_findings='all' is not honored" in warning for warning in result["warnings"]
    )


def test_scorecard_defaults_alone_cannot_approve_findings() -> None:
    """Top-level scorecard_defaults must not approve without per-repo scorecard block."""
    feedback = {
        "scorecard_defaults": {
            "decision": "approve",
            "approved_findings": ["scorecard:Branch-Protection"],
            "dropped_findings": [],
            "priority": "normal",
        },
        "decisions": {
            "stranske/Workflows": {
                "decision": "defer",
            }
        },
    }
    result = approved_scorecard_issue_items(_sample_scan(), feedback, "2026-06-14")
    assert result["issues"] == []
    assert len(result["pending"]) == 2


def test_approved_scorecard_candidate_index_starts_at_9000_after_dropped() -> None:
    feedback = {
        "scorecard_defaults": {"decision": "defer", "approved_findings": []},
        "decisions": {
            "stranske/Workflows": {
                "scorecard": {
                    "decision": "approve",
                    "approved_findings": ["scorecard:Branch-Protection"],
                    "dropped_findings": ["scorecard:Token-Permissions"],
                    "priority": "normal",
                    "priority_overrides": {},
                }
            }
        },
    }
    result = approved_scorecard_issue_items(_sample_scan(), feedback, "2026-06-14")
    assert len(result["issues"]) == 1
    assert result["issues"][0]["candidate_index"] == 9000
    assert len(result["dropped"]) == 1


def test_approved_scorecard_issue_items_materializes_explicit_approval() -> None:
    feedback = {
        "scorecard_defaults": {"decision": "defer", "approved_findings": []},
        "decisions": {
            "stranske/Workflows": {
                "scorecard": {
                    "decision": "approve",
                    "approved_findings": ["scorecard:Branch-Protection"],
                    "dropped_findings": [],
                    "priority": "normal",
                    "priority_overrides": {"scorecard:Branch-Protection": "high"},
                    "notes": "Approved after review.",
                }
            }
        },
    }
    result = approved_scorecard_issue_items(_sample_scan(), feedback, "2026-06-14")
    assert len(result["issues"]) == 1
    issue = result["issues"][0]
    assert issue["candidate_index"] == 9000
    assert issue["source_type"] == "scorecard finding"
    assert issue["source"] == "OpenSSF Scorecard"
    assert issue["scorecard_finding_id"] == "scorecard:Branch-Protection"
    assert issue["priority"] == "high"
    assert issue_body_quality_errors(issue["body"]) == []


def test_load_scorecard_scan_rejects_wrong_schema(tmp_path: Path) -> None:
    path = tmp_path / "scorecard-scan.json"
    path.write_text('{"schema": "other", "by_repo": []}\n', encoding="utf-8")
    assert load_scorecard_scan(path) is None


def test_scan_scorecard_repos_uses_fixture_fetcher(tmp_path: Path) -> None:
    docs_config = tmp_path / "source_of_truth_docs.yml"
    docs_config.write_text(
        yaml.safe_dump(
            {
                "scorecard": {
                    "enabled": True,
                    "default_minimum_score": 7.0,
                    "max_findings_per_repo": 5,
                },
                "repos": {
                    "stranske/Workflows": {
                        "local_path": "Workflows-steward",
                        "scorecard": {
                            "enabled": True,
                            "minimum_score": 7.0,
                            "workflow": ".github/workflows/health-53-scorecard.yml",
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    config = load_scorecard_config(docs_config)
    payload = json.loads(FIXTURE_API.read_text(encoding="utf-8"))

    def fetcher(repo: str):
        assert repo == "stranske/Workflows"
        return True, payload, None

    result = scan_scorecard_repos(
        scorecard_config=config,
        active_repos={"stranske/Workflows"},
        fetcher=fetcher,
    )
    assert result["schema"] == SCHEMA
    assert result["total_findings"] == 2
    assert result["by_repo"][0]["repo"] == "stranske/Workflows"


def test_scan_scorecard_repos_skips_repos_without_explicit_scorecard_block(tmp_path: Path) -> None:
    docs_config = tmp_path / "source_of_truth_docs.yml"
    docs_config.write_text(
        yaml.safe_dump(
            {
                "scorecard": {
                    "enabled": True,
                    "default_minimum_score": 7.0,
                },
                "repos": {
                    "stranske/Workflows": {
                        "local_path": "Workflows-steward",
                        "scorecard": {"enabled": True, "minimum_score": 7.0},
                    },
                    "stranske/Template": {
                        "local_path": "Template",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    config = load_scorecard_config(docs_config)
    calls: list[str] = []

    def fetcher(repo: str):
        calls.append(repo)
        return True, {"checks": []}, None

    result = scan_scorecard_repos(
        scorecard_config=config,
        active_repos={"stranske/Workflows", "stranske/Template"},
        fetcher=fetcher,
    )
    assert calls == ["stranske/Workflows"]
    assert [bucket["repo"] for bucket in result["by_repo"]] == ["stranske/Workflows"]


def test_format_scorecard_section_renders_one_section_per_repo() -> None:
    rendered = format_scorecard_section(_sample_scan())
    assert rendered.count("## Scorecard findings need explicit approval") == 1
    assert rendered.count("### stranske/Workflows") == 1
    assert "config/repo_review_feedback.json" in rendered
    assert "gh issue create" not in rendered
    assert "repo_review_evaluator.py" in rendered


def test_format_scorecard_section_includes_approval_snippet() -> None:
    rendered = format_scorecard_section(_sample_scan())
    assert "approved_findings" in rendered
    assert "scorecard:Branch-Protection" in rendered
    assert 'decisions["stranske/Workflows"].scorecard' in rendered
