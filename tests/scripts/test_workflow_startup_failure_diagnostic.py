from __future__ import annotations

from typing import Any

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


def test_classify_startup_failure_action_resolution() -> None:
    phase, root = diag._classify_startup_failure(
        summary="Unable to resolve action `owner/repo@main`",
        title="Startup failure",
        text="Repository not found",
    )
    assert phase == "action_resolution"
    assert root == "action_reference_or_access"


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
