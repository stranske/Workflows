from __future__ import annotations

from typing import Any

import pytest
from scripts import workflow_startup_failure_diagnostic as diag


def test_collect_startup_failures_filters_by_run_and_conclusion() -> None:
    payload = {
        "check_runs": [
            {
                "id": 1,
                "conclusion": "success",
                "details_url": "https://github.com/o/r/actions/runs/123",
            },
            {
                "id": 2,
                "conclusion": "startup_failure",
                "details_url": "https://github.com/o/r/actions/runs/123/job/1",
            },
            {
                "id": 3,
                "conclusion": "startup_failure",
                "details_url": "https://github.com/o/r/actions/runs/999/job/1",
            },
        ]
    }
    matches = diag._collect_startup_failures(payload, run_id=123)
    assert [m["id"] for m in matches] == [2]


def test_collect_startup_failures_ignores_malformed_payloads() -> None:
    assert diag._collect_startup_failures({"check_runs": {"id": 1}}, run_id=123) == []
    assert diag._collect_startup_failures({"check_runs": None}, run_id=123) == []


def test_collect_startup_failures_ignores_non_dict_entries() -> None:
    payload = {
        "check_runs": [
            None,
            "not-a-check-run",
            42,
            {
                "id": 7,
                "conclusion": "startup_failure",
                "details_url": "https://github.com/o/r/actions/runs/123/job/1",
            },
        ]
    }

    matches = diag._collect_startup_failures(payload, run_id=123)

    assert [m["id"] for m in matches] == [7]


def test_gh_api_rejects_non_object_response(monkeypatch) -> None:
    def fail_if_token_requested() -> str:
        raise AssertionError("gh auth token should not be called when token is supplied")

    def fake_request_json(
        method: str,
        url: str,
        token: str,
        payload: object | None = None,
    ) -> list[str]:
        assert method == "GET"
        assert url.endswith("/repos/owner/repo/actions/runs/123")
        assert token == "test-token"
        assert payload is None
        return ["not", "an", "object"]

    monkeypatch.setattr(diag, "_github_token", fail_if_token_requested)
    monkeypatch.setattr(diag.api_client, "_request_json", fake_request_json)

    with pytest.raises(ValueError, match="Expected JSON object"):
        diag._gh_api("repos/owner/repo/actions/runs/123", token="test-token")


def test_diagnose_startup_failure_collects_output_fields(monkeypatch) -> None:
    responses = [
        {
            "head_sha": "abc123",
            "name": "Gate",
            "conclusion": "startup_failure",
            "status": "completed",
        },
        {"jobs": []},
        {
            "check_runs": [
                {
                    "id": 42,
                    "name": "Gate / detect",
                    "status": "completed",
                    "conclusion": "startup_failure",
                    "details_url": "https://github.com/o/r/actions/runs/555",
                    "html_url": "https://github.com/o/r/runs/42",
                    "output": {
                        "title": "The workflow is not valid",
                        "summary": "Unrecognized named-value: 'needs'",
                        "text": "Line 123",
                    },
                }
            ]
        },
    ]

    def fake_gh_api(path: str, token: str | None = None) -> dict[str, Any]:
        assert token is None
        assert path.startswith("repos/owner/repo/")
        return responses.pop(0)

    monkeypatch.setattr(diag, "_gh_api", fake_gh_api)
    report = diag.diagnose_startup_failure("owner/repo", 555)

    assert report["jobs_count"] == 0
    assert report["head_sha"] == "abc123"
    assert len(report["startup_failures"]) == 1
    finding = report["startup_failures"][0]
    assert finding["title"] == "The workflow is not valid"
    assert "Unrecognized named-value" in finding["summary"]
    assert finding["failure_phase"] == "workflow_parse_or_graph"
    assert finding["suspected_root_cause"] == "invalid_expression_context_reference"


def test_diagnose_startup_failure_rejects_missing_head_sha(monkeypatch) -> None:
    responses = [
        {"name": "Gate", "conclusion": "startup_failure", "status": "completed"},
        {"jobs": []},
    ]
    requested_paths: list[str] = []

    def fake_gh_api(path: str, token: str | None = None) -> dict[str, Any]:
        assert token is None
        requested_paths.append(path)
        return responses.pop(0)

    monkeypatch.setattr(diag, "_gh_api", fake_gh_api)

    with pytest.raises(ValueError, match="missing head_sha"):
        diag.diagnose_startup_failure("owner/repo", 555)

    assert requested_paths == [
        "repos/owner/repo/actions/runs/555",
        "repos/owner/repo/actions/runs/555/jobs",
    ]


def test_classify_startup_failure_action_resolution() -> None:
    phase, root = diag._classify_startup_failure(
        summary="Unable to resolve action `owner/repo@main`",
        title="Startup failure",
        text="Repository not found",
    )
    assert phase == "action_resolution"
    assert root == "action_reference_or_access"


@pytest.mark.parametrize(
    ("summary", "title", "text", "expected_root"),
    [
        (
            "Unexpected value 'uses'",
            "The workflow is not valid",
            "Line 14, Col 9",
            "yaml_structure_or_syntax",
        ),
        (
            "The template is not valid. fromJson received invalid JSON input.",
            "The workflow is not valid",
            "Line 22, Col 17",
            "expression_type_or_json_coercion",
        ),
    ],
)
def test_classify_startup_failure_parse_causes(
    summary: str,
    title: str,
    text: str,
    expected_root: str,
) -> None:
    phase, root = diag._classify_startup_failure(summary=summary, title=title, text=text)

    assert phase == "workflow_parse_or_graph"
    assert root == expected_root


def test_main_returns_2_when_no_startup_failure(monkeypatch, capsys) -> None:
    responses = [
        {"head_sha": "abc123", "name": "Gate", "conclusion": "failure", "status": "completed"},
        {"jobs": []},
        {"check_runs": []},
    ]

    def fake_gh_api(path: str, token: str | None = None) -> dict[str, Any]:
        return responses.pop(0)

    monkeypatch.setattr(diag, "_gh_api", fake_gh_api)
    exit_code = diag.main(["--repo", "owner/repo", "--run-id", "111"])

    assert exit_code == 2
    assert "No matching startup_failure check-runs found" in capsys.readouterr().err


def test_main_returns_1_when_diagnosis_raises(monkeypatch, capsys) -> None:
    def fake_diagnose_startup_failure(repo: str, run_id: int) -> dict[str, Any]:
        assert repo == "owner/repo"
        assert run_id == 111
        raise ValueError("Run 111 in owner/repo is missing head_sha")

    monkeypatch.setattr(diag, "diagnose_startup_failure", fake_diagnose_startup_failure)

    exit_code = diag.main(["--repo", "owner/repo", "--run-id", "111"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "workflow_startup_failure_diagnostic:" in captured.err
    assert "missing head_sha" in captured.err
