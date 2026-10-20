"""Tests for scripts/repo_review_scorecard.py."""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import yaml
from scripts import repo_review_scorecard
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


def test_scorecard_loaders_and_parsers_reject_invalid_inputs(tmp_path: Path) -> None:
    assert load_scorecard_scan(None) is None
    assert load_scorecard_scan(tmp_path / "missing.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert load_scorecard_scan(bad) is None
    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    assert load_scorecard_scan(array) is None
    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps({"schema": SCHEMA}), encoding="utf-8")
    assert load_scorecard_scan(valid) == {"schema": SCHEMA}

    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps({"repos": [{"repo": "one", "status": "active"}, {"repo": "two"}, "bad"]}),
        encoding="utf-8",
    )
    assert repo_review_scorecard.load_active_repos(registry) == {"one"}
    assert parse_scorecard_api_response({"checks": "invalid"}) == []
    assert parse_scorecard_api_response(
        {"checks": ["bad", {}, {"name": "  "}, {"name": "Check", "score": "2.5"}]}
    ) == [
        {
            "check": "Check",
            "score": 2.5,
            "reason": "",
            "details": [],
            "documentation_url": "",
        }
    ]


def test_scorecard_filter_and_metadata_helpers_cover_edges() -> None:
    findings, skipped = filter_scorecard_findings(
        [
            {"check": "too-high", "score": 7},
            {"check": "excluded", "score": 1},
            {"check": "included", "score": 1},
            {"check": "overflow", "score": 2},
        ],
        minimum_score=7,
        include_checks=["excluded", "included", "overflow"],
        exclude_checks=["excluded"],
        max_findings_per_repo=1,
        source_url="url",
    )
    assert findings[0]["check"] == "included"
    assert {item["reason"] for item in skipped} == {
        "not in include_checks",
        "listed in exclude_checks",
        "capped by max_findings_per_repo=1",
    }
    assert repo_review_scorecard.normalize_priority("HIGH") == "high"
    assert repo_review_scorecard.normalize_priority("unknown") == "normal"
    assert repo_review_scorecard.scorecard_priority(3) == "high"
    assert repo_review_scorecard.scorecard_priority(3.1) == "normal"
    assert repo_review_scorecard.scorecard_api_url("owner/repo").endswith("github.com/owner/repo")
    assert repo_review_scorecard.scorecard_labels("bad") == [
        "repo-review-approved",
        "priority:normal",
    ]
    assert repo_review_scorecard.dry_run_fetcher("owner/repo") == (True, {"checks": []}, None)


def test_scorecard_approval_paths_and_quality_gate(monkeypatch) -> None:
    assert repo_review_scorecard.approved_scorecard_issue_items(None, {}, "today")["issues"] == []
    scan = _sample_scan()
    scan["by_repo"].extend(["bad", {"repo": "", "findings": []}])
    feedback = {
        "scorecard_defaults": "bad",
        "decisions": {
            "stranske/Workflows": {
                "approved_candidates": "all",
                "scorecard": {
                    "decision": "approve",
                    "approved_findings": ["scorecard:Branch-Protection"],
                    "dropped_findings": ["scorecard:Token-Permissions"],
                    "priority": "bad",
                    "priority_overrides": "bad",
                },
            }
        },
    }
    result = repo_review_scorecard.approved_scorecard_issue_items(scan, feedback, "today")
    assert len(result["issues"]) == 1
    assert len(result["dropped"]) == 1

    monkeypatch.setattr(
        repo_review_scorecard, "issue_body_quality_errors", lambda _body: ["broken"]
    )
    result = repo_review_scorecard.approved_scorecard_issue_items(_sample_scan(), feedback, "today")
    assert result["issues"] == []
    assert any(
        item["reason"] == "scorecard issue body failed quality gate" for item in result["pending"]
    )


def test_fetch_scorecard_api_handles_response_types_and_errors(monkeypatch) -> None:
    class Response:
        def read(self):
            return b'{"checks": []}'

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(
        repo_review_scorecard.urllib.request, "urlopen", lambda *_args, **_kwargs: Response()
    )
    assert repo_review_scorecard.fetch_scorecard_api("owner/repo") == (True, {"checks": []}, None)
    monkeypatch.setattr(
        repo_review_scorecard.urllib.request, "urlopen", lambda *_args, **_kwargs: Response()
    )
    assert repo_review_scorecard.fetch_scorecard_api("owner/repo", timeout=1)[0]

    def http_error(*_args, **_kwargs):
        raise urllib.error.HTTPError("url", 404, "missing", {}, None)

    monkeypatch.setattr(repo_review_scorecard.urllib.request, "urlopen", http_error)
    assert "HTTP 404" in (repo_review_scorecard.fetch_scorecard_api("owner/repo")[2] or "")
    monkeypatch.setattr(
        repo_review_scorecard.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    assert "network error" in (repo_review_scorecard.fetch_scorecard_api("owner/repo")[2] or "")


def test_scan_and_main_cover_disabled_failures_and_cli(monkeypatch, tmp_path: Path, capsys) -> None:
    config = {
        "defaults": {"enabled": True, "include_checks": [], "exclude_checks": []},
        "repos": {
            "inactive": {"explicit_scorecard": True, "scorecard": {}},
            "disabled": {"explicit_scorecard": True, "scorecard": {"enabled": False}},
            "bad": {"explicit_scorecard": True, "scorecard": "bad"},
            "enabled": {"explicit_scorecard": True, "local_path": "x", "scorecard": {}},
        },
    }
    result = scan_scorecard_repos(
        scorecard_config=config,
        active_repos={"disabled", "bad", "enabled"},
        fetcher=lambda _repo: (False, None, "offline"),
    )
    assert result["total_errors"] == 2
    assert [item["repo"] for item in result["by_repo"]] == ["bad", "enabled"]

    out = tmp_path / "nested" / "scan.json"
    monkeypatch.setattr(
        repo_review_scorecard,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "docs_config": Path("docs"),
                "registry": Path("registry"),
                "repos": [],
                "dry_run": True,
                "out": out,
            },
        )(),
    )
    monkeypatch.setattr(repo_review_scorecard, "load_scorecard_config", lambda _path: config)
    monkeypatch.setattr(repo_review_scorecard, "load_active_repos", lambda _path: {"enabled"})
    assert repo_review_scorecard.main() == 0
    assert json.loads(out.read_text(encoding="utf-8"))["by_repo"]
    assert "scanned 1 repo" in capsys.readouterr().out


def test_scorecard_cli_parse_and_main_load_failures(monkeypatch, tmp_path: Path, capsys) -> None:
    registry = tmp_path / "registry.json"
    docs = tmp_path / "docs.yml"
    out = tmp_path / "scan.json"
    monkeypatch.setattr(
        repo_review_scorecard.sys,
        "argv",
        [
            "script",
            "--registry",
            str(registry),
            "--docs-config",
            str(docs),
            "--out",
            str(out),
            "--repos",
            "owner/one",
            "owner/two",
            "--dry-run",
        ],
    )
    args = repo_review_scorecard.parse_args()
    assert args.registry == registry
    assert args.docs_config == docs
    assert args.out == out
    assert args.repos == ["owner/one", "owner/two"]
    assert args.dry_run

    monkeypatch.setattr(
        repo_review_scorecard,
        "load_scorecard_config",
        lambda _path: (_ for _ in ()).throw(FileNotFoundError("missing")),
    )
    assert repo_review_scorecard.main() == 2
    assert "cannot load docs config" in capsys.readouterr().err

    monkeypatch.setattr(repo_review_scorecard, "load_scorecard_config", lambda _path: {})
    monkeypatch.setattr(
        repo_review_scorecard,
        "load_active_repos",
        lambda _path: (_ for _ in ()).throw(json.JSONDecodeError("bad", "", 0)),
    )
    assert repo_review_scorecard.main() == 2
    assert "cannot load registry" in capsys.readouterr().err


def test_fetch_scorecard_api_rejects_non_object_and_timeout(monkeypatch) -> None:
    class ArrayResponse:
        def read(self):
            return b"[]"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(
        repo_review_scorecard.urllib.request, "urlopen", lambda *_args, **_kwargs: ArrayResponse()
    )
    assert "unexpected payload type" in (
        repo_review_scorecard.fetch_scorecard_api("owner/repo")[2] or ""
    )
    monkeypatch.setattr(
        repo_review_scorecard.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("slow")),
    )
    assert repo_review_scorecard.fetch_scorecard_api("owner/repo") == (False, None, "slow")
