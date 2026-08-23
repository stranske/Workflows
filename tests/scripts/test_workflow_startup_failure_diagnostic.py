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
    assert report["approval_hold"] is None
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
    assert "No matching startup_failure check-runs or zero-job approval hold" in (
        capsys.readouterr().err
    )


def test_diagnose_zero_job_action_required_as_web_approval_hold(monkeypatch) -> None:
    responses = [
        {
            "head_sha": "abc123",
            "name": "Auto-Label Issues",
            "conclusion": "action_required",
            "status": "completed",
            "event": "issues",
        },
        {"jobs": []},
        {"check_runs": []},
    ]

    def fake_gh_api(path: str, token: str | None = None) -> dict[str, Any]:
        return responses.pop(0)

    monkeypatch.setattr(diag, "_gh_api", fake_gh_api)
    report = diag.diagnose_startup_failure("owner/repo", 555)

    assert report["approval_hold"] == {
        "failure_phase": "pre_job_workflow_approval",
        "suspected_root_cause": "github_unproven_workflow_protection",
        "approval_url": "https://github.com/owner/repo/actions/runs/555",
        "remediation": (
            "Review the workflow file, then use Approve and run from an "
            "authenticated GitHub web session. The workflow-run approval "
            "REST endpoint does not cover this protection."
        ),
    }


def test_diagnose_zero_job_fork_pr_as_rest_approvable_hold(monkeypatch) -> None:
    responses = [
        {
            "head_sha": "abc123",
            "name": "CI",
            "conclusion": "action_required",
            "status": "completed",
            "event": "pull_request",
            "head_repository": {"full_name": "contributor/repo", "fork": True},
        },
        {"jobs": []},
        {"check_runs": []},
    ]

    def fake_gh_api(path: str, token: str | None = None) -> dict[str, Any]:
        return responses.pop(0)

    monkeypatch.setattr(diag, "_gh_api", fake_gh_api)
    report = diag.diagnose_startup_failure("owner/repo", 555)

    assert report["approval_hold"] == {
        "failure_phase": "pre_job_workflow_approval",
        "suspected_root_cause": "fork_contributor_approval_hold",
        "approval_url": "https://github.com/owner/repo/actions/runs/555",
        "remediation": (
            "Public-fork pull-request runs awaiting contributor approval can be "
            "recovered with POST /repos/{owner}/{repo}/actions/runs/{run_id}/approve "
            "(or Approve and run in the GitHub UI)."
        ),
    }


def test_diagnose_zero_job_pr_without_head_repo_is_unspecified(monkeypatch) -> None:
    responses = [
        {
            "head_sha": "abc123",
            "name": "CI",
            "conclusion": "action_required",
            "status": "completed",
            "event": "pull_request",
        },
        {"jobs": []},
        {"check_runs": []},
    ]

    def fake_gh_api(path: str, token: str | None = None) -> dict[str, Any]:
        return responses.pop(0)

    monkeypatch.setattr(diag, "_gh_api", fake_gh_api)
    report = diag.diagnose_startup_failure("owner/repo", 555)

    hold = report["approval_hold"]
    assert hold is not None
    assert hold["suspected_root_cause"] == "workflow_approval_hold_unspecified"
    assert "head_repository.fork" in hold["remediation"]


def test_main_accepts_zero_job_action_required_hold(monkeypatch, capsys) -> None:
    responses = [
        {
            "head_sha": "abc123",
            "name": "Auto-Label Issues",
            "conclusion": "action_required",
            "status": "completed",
            "event": "issues",
        },
        {"jobs": []},
        {"check_runs": []},
    ]

    def fake_gh_api(path: str, token: str | None = None) -> dict[str, Any]:
        return responses.pop(0)

    monkeypatch.setattr(diag, "_gh_api", fake_gh_api)
    exit_code = diag.main(["--repo", "owner/repo", "--run-id", "555"])

    assert exit_code == 0
    assert "pre_job_workflow_approval" in capsys.readouterr().out


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


# --- liveness sweep ---------------------------------------------------------
#
# The sweep is the executable form of the DURABLE_TRACKING_ISSUES.md oracle:
# confirm liveness from run history, not from tracker activity. A held workflow
# emits no jobs, no logs and no annotations, so these tests are the only thing
# standing between a silent fleet-wide outage and a green sweep.


def _sweep_stub(
    *,
    runs: list[dict[str, Any]],
    jobs: list[dict[str, Any]] | None = None,
    onset_pages: list[list[dict[str, Any]]] | None = None,
    workflow_path: str = ".github/workflows/agents-dedup.yml",
):
    """Build a path-dispatching _gh_api fake for one active workflow."""
    pages = onset_pages if onset_pages is not None else [runs]

    def fake_gh_api(path: str, token: str | None = None) -> dict[str, Any]:
        if "/actions/workflows?" in path:
            return {
                "workflows": [{"id": 7, "state": "active", "name": "Dedup", "path": workflow_path}]
            }
        if "/jobs" in path:
            return {"jobs": jobs or []}
        if "per_page=100" in path:
            page = int(path.rsplit("page=", 1)[-1])
            batch = pages[page - 1] if page <= len(pages) else []
            return {"workflow_runs": batch}
        if "/runs?" in path:
            return {"workflow_runs": runs}
        raise AssertionError(f"unexpected path {path}")

    return fake_gh_api


def _held_run(run_id: int, created: str, event: str = "issues") -> dict[str, Any]:
    return {
        "id": run_id,
        "conclusion": "action_required",
        "status": "completed",
        "event": event,
        "created_at": created,
        "head_repository": {"full_name": "owner/repo", "fork": False},
    }


def test_sweep_flags_zero_job_hold_and_reports_it_as_undrainable(monkeypatch) -> None:
    runs = [_held_run(100 + i, f"2026-08-2{i % 3}T00:00:00Z") for i in range(20)]
    monkeypatch.setattr(diag, "_gh_api", _sweep_stub(runs=runs))

    report = diag.sweep(["owner/repo"], token="t", now="2026-08-23T00:00:00Z")

    assert report["held_count"] == 1
    assert report["drainable_count"] == 0
    entry = report["held"][0]
    assert entry["workflow"] == ".github/workflows/agents-dedup.yml"
    assert entry["suspected_root_cause"] == "github_unproven_workflow_protection"
    assert entry["drainable_by_api"] is False


def test_sweep_ignores_holds_that_created_jobs(monkeypatch) -> None:
    """Jobs present means a deployment/environment gate, a different class."""
    runs = [_held_run(200 + i, "2026-08-01T00:00:00Z") for i in range(20)]
    monkeypatch.setattr(
        diag, "_gh_api", _sweep_stub(runs=runs, jobs=[{"name": "waiting", "status": "queued"}])
    )

    report = diag.sweep(["owner/repo"], token="t", now="2026-08-23T00:00:00Z")

    assert report["held_count"] == 0


def test_sweep_counts_fork_pr_hold_as_drainable(monkeypatch) -> None:
    runs = [
        {
            "id": 300 + i,
            "conclusion": "action_required",
            "status": "completed",
            "event": "pull_request",
            "created_at": "2026-08-20T00:00:00Z",
            "head_repository": {"full_name": "contributor/repo", "fork": True},
        }
        for i in range(20)
    ]
    monkeypatch.setattr(diag, "_gh_api", _sweep_stub(runs=runs))

    report = diag.sweep(["owner/repo"], token="t", now="2026-08-23T00:00:00Z")

    assert report["held_count"] == 1
    assert report["drainable_count"] == 1
    assert report["held"][0]["drainable_by_api"] is True


def test_sweep_onset_walks_past_the_sample_page(monkeypatch) -> None:
    """Regression guard: the onset must not be read off the sample page.

    A workflow triggered hourly discards 20 runs in under a day. If the onset is
    taken from the sample instead of paginating to the last run that executed, a
    22-day outage reports as hours old and the sweep reads as harmless. Deleting
    the pagination in _find_hold_onset turns days_held from 22 into 0 and fails
    this test.
    """
    recent = [_held_run(400 + i, "2026-08-22T12:00:00Z") for i in range(100)]
    older = [_held_run(500 + i, "2026-08-01T00:00:00Z") for i in range(50)]
    older.append({"id": 999, "conclusion": "success", "created_at": "2026-07-31T16:30:01Z"})
    monkeypatch.setattr(
        diag,
        "_gh_api",
        _sweep_stub(runs=recent[:20], onset_pages=[recent, older]),
    )

    report = diag.sweep(["owner/repo"], token="t", now="2026-08-23T00:00:00Z")

    entry = report["held"][0]
    assert entry["onset"] == "2026-08-01T00:00:00Z"
    assert entry["days_held"] == 22
    assert entry["onset_truncated"] is False
    assert entry["consecutive_held"] == 150


def test_sweep_summary_always_carries_blocking_and_drainable(monkeypatch) -> None:
    runs = [_held_run(600 + i, "2026-08-01T00:00:00Z") for i in range(20)]
    monkeypatch.setattr(diag, "_gh_api", _sweep_stub(runs=runs))

    report = diag.sweep(["owner/repo"], token="t", now="2026-08-23T00:00:00Z")
    summary = diag.format_sweep_summary(report)

    # "1 held" alone reads as a backlog; the pair reads as a deadlock.
    assert "1 held" in summary
    assert "0 clearable by API" in summary
    assert "web approval required" in summary


def test_sweep_green_summary_states_what_it_checked() -> None:
    empty = {
        "held_count": 0,
        "drainable_count": 0,
        "workflows_scanned": 128,
        "held_runs_discarded": 0,
        "oldest_hold": None,
        "held": [],
    }
    summary = diag.format_sweep_summary(empty)
    assert "0 held" in summary
    assert "128 active workflows scanned" in summary


def test_sweep_main_fails_on_hold_and_report_only_passes(monkeypatch) -> None:
    runs = [_held_run(700 + i, "2026-08-01T00:00:00Z") for i in range(20)]
    monkeypatch.setattr(diag, "_gh_api", _sweep_stub(runs=runs))
    monkeypatch.setattr(diag, "_github_token", lambda: "t")

    assert diag.main(["--sweep", "--repo", "owner/repo"]) == 1
    assert diag.main(["--sweep", "--repo", "owner/repo", "--report-only"]) == 0


def test_sweep_requires_a_repository(capsys) -> None:
    assert diag.main(["--sweep"]) == 1
    assert "--sweep needs --repo" in capsys.readouterr().err
