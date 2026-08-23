from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from scripts import workflow_startup_failure_diagnostic as diag


@pytest.fixture(autouse=True)
def _list_endpoint_follows_the_object_stub(monkeypatch):
    """Route _gh_api_list through whatever _gh_api a test installed.

    review_hold reads the commits endpoint, whose success body is an ARRAY, so it
    uses _gh_api_list. Tests stub _gh_api only; without this the list call escapes
    to the real network. Resolved at call time so fixture/monkeypatch order does
    not matter.
    """
    monkeypatch.setattr(diag, "_gh_api_list", lambda path, token=None: diag._gh_api(path, token))


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
        **kwargs: object,
    ) -> list[str]:
        assert method == "GET"
        assert url.endswith("/repos/owner/repo/actions/runs/123")
        assert token == "test-token"
        assert payload is None
        # A secondary rate limit needs a minute or more; api_client's defaults
        # (3 attempts, 1s backoff) give up in ~3 seconds, so the sweep must pass
        # its own policy or the daily job dies on its own traffic.
        assert kwargs["max_attempts"] >= 5
        assert kwargs["backoff"] >= 4
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
    commits: list[dict[str, Any]] | None = None,
    patch: str = "",
):
    """Build a path-dispatching _gh_api fake for one active workflow.

    Also serves the two commit endpoints the auto-review uses, so a test that
    only cares about hold detection does not have to describe a diff.
    """
    pages = onset_pages if onset_pages is not None else [runs]

    def fake_gh_api(path: str, token: str | None = None) -> Any:
        if "/actions/workflows?" in path:
            return {
                "workflows": [{"id": 7, "state": "active", "name": "Dedup", "path": workflow_path}]
            }
        if "/jobs" in path:
            return {"jobs": jobs or []}
        if "/commits?" in path:
            return commits or []
        if "/commits/" in path:
            return {"files": [{"filename": workflow_path, "patch": patch}]}
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


def test_sweep_does_not_report_a_workflow_that_has_recovered(monkeypatch) -> None:
    """Regression guard for a defect that shipped in the first sweep.

    A long outage fills the sample window with held runs. When the workflow is
    finally approved and executes, the held SHARE is still ~95%, so a
    share-based rule keeps reporting it as held forever - the detector cries
    wolf and becomes as useless as the silence it replaced. Held must be decided
    by the NEWEST run.

    Deleting the `runs[0].get("conclusion") != HELD_RUN_CONCLUSION` guard in
    sweep_repository makes this test fail with held_count == 1.
    """
    recovered = [
        {
            "id": 900,
            "conclusion": "success",
            "status": "completed",
            "event": "workflow_run",
            "created_at": "2026-08-23T05:21:42Z",
        }
    ] + [_held_run(800 + i, "2026-08-01T00:00:00Z") for i in range(19)]
    monkeypatch.setattr(diag, "_gh_api", _sweep_stub(runs=recovered))

    report = diag.sweep(["owner/repo"], token="t", now="2026-08-23T06:00:00Z")

    assert report["held_count"] == 0
    assert "0 held" in diag.format_sweep_summary(report)


def test_sweep_still_reports_a_single_fresh_hold(monkeypatch) -> None:
    """Early detection matters: one held newest run is already an outage.

    A share threshold would have suppressed this (1 held of 20 = 5%), which is
    exactly the just-edited-and-blocked case the sweep exists to catch in a day
    rather than three weeks.
    """
    runs = [_held_run(1000, "2026-08-23T05:00:00Z")] + [
        {
            "id": 1001 + i,
            "conclusion": "success",
            "status": "completed",
            "event": "issues",
            "created_at": "2026-08-22T00:00:00Z",
        }
        for i in range(19)
    ]
    monkeypatch.setattr(diag, "_gh_api", _sweep_stub(runs=runs, onset_pages=[runs]))

    report = diag.sweep(["owner/repo"], token="t", now="2026-08-23T05:30:00Z")

    assert report["held_count"] == 1
    assert report["held"][0]["consecutive_held"] == 1


def test_fmt_days_never_prints_a_bare_none() -> None:
    assert diag._fmt_days({"days_held": None}) == "age unknown"
    assert diag._fmt_days({"days_held": 22, "onset_truncated": False}) == "22d"
    assert diag._fmt_days({"days_held": 9, "onset_truncated": True}) == ">=9d"


# --- auto-review ------------------------------------------------------------
#
# Clearing a hold costs a human ~5 seconds of clicking and ~2 minutes of working
# out whether the file is safe to approve. The second part is mechanical, so the
# sweep does it: diff the file against its last healthy run and say whether any
# ADDED line is the kind of thing a reviewer must actually look at.
#
# The verdict is decision support, never authorisation. Nothing here approves.


def _commit(sha: str, subject: str) -> dict[str, Any]:
    return {"sha": sha, "commit": {"message": subject}}


def test_review_reports_benign_when_nothing_risky_was_added(monkeypatch) -> None:
    monkeypatch.setattr(
        diag,
        "_gh_api",
        _sweep_stub(
            runs=[],
            commits=[_commit("abc12345", "chore(deps): bump actions/setup-python to v7")],
            patch="@@\n-          python-version: '3.13'\n+          python-version: '3.14'\n",
        ),
    )
    out = diag.review_hold("owner/repo", ".github/workflows/agents-dedup.yml", "2026-08-01", "t")
    assert out["verdict"] == "benign"
    assert out["commits"][0]["sha"] == "abc12345"


def test_review_flags_event_interpolation_added_to_a_body(monkeypatch) -> None:
    monkeypatch.setattr(
        diag,
        "_gh_api",
        _sweep_stub(
            runs=[],
            commits=[_commit("def67890", "fix: recheck eligibility")],
            patch='@@\n+            gh issue view "${{ github.event.issue.number }}" --json labels\n',
        ),
    )
    out = diag.review_hold("owner/repo", ".github/workflows/agents-dedup.yml", "2026-08-01", "t")
    assert out["verdict"] == "needs-eyes"
    assert "interpolated" in out["reason"]


def test_review_says_no_edit_when_the_file_was_never_touched(monkeypatch) -> None:
    monkeypatch.setattr(diag, "_gh_api", _sweep_stub(runs=[], commits=[]))
    out = diag.review_hold("owner/repo", ".github/workflows/x.yml", "2026-08-01", "t")
    assert out["verdict"] == "no-edit"


def test_review_does_not_call_an_error_body_benign(monkeypatch) -> None:
    """A failed commit lookup must never read as reassuring.

    The commits endpoint returns a bare array; an object is an error body. Treating
    that as "no commits" would print `benign` for a file nobody managed to inspect
    - the same silent-plausible-wrongness this whole sweep exists to remove.
    """

    def boom(path, token=None):
        raise ValueError("404 Not Found")

    monkeypatch.setattr(diag, "_gh_api_list", boom)
    out = diag.review_hold("owner/repo", ".github/workflows/x.yml", "2026-08-01", "t")
    assert out["verdict"] == "unknown"
    assert out["verdict"] != "benign"


def test_review_verdict_unknown_without_a_healthy_run() -> None:
    out = diag.review_hold("owner/repo", ".github/workflows/x.yml", None, "t")
    assert out["verdict"] == "unknown"


def test_sweep_summary_reports_the_triage_split(monkeypatch) -> None:
    runs = [_held_run(1200 + i, "2026-08-01T00:00:00Z") for i in range(20)]
    history = runs + [{"id": 1199, "conclusion": "success", "created_at": "2026-07-31T00:00:00Z"}]
    monkeypatch.setattr(
        diag,
        "_gh_api",
        _sweep_stub(
            runs=runs,
            onset_pages=[history],
            commits=[_commit("aaa11111", "chore: bump pin")],
            patch="@@\n+          python-version: '3.14'\n",
        ),
    )
    report = diag.sweep(["owner/repo"], token="t", now="2026-08-23T00:00:00Z")
    assert report["held_count"] == 1
    assert report["benign_count"] == 1
    assert report["needs_eyes_count"] == 0
    assert "1 benign, 0 need eyes" in diag.format_sweep_summary(report)


def test_review_does_not_repaginate_run_history(monkeypatch) -> None:
    """Cost guard: the onset walk and the review share one pass over run history.

    In CI this sweep spends the GitHub App INSTALLATION token, which every
    workflow in the fleet shares and which was observed exhausted at 5000/5000
    while workflows were resuming. An earlier draft walked the run pages twice per
    held workflow - once for the onset, once to find the last healthy run - which
    doubled the cost of the most expensive part for no new information, since the
    run that ends the held streak IS the last healthy run.
    """
    runs = [_held_run(1300 + i, "2026-08-20T00:00:00Z") for i in range(20)]
    history = runs + [{"id": 1299, "conclusion": "success", "created_at": "2026-08-01T00:00:00Z"}]
    calls: list[str] = []
    inner = _sweep_stub(
        runs=runs,
        onset_pages=[history],
        commits=[_commit("bbb22222", "chore: bump")],
        patch="@@\n+          python-version: '3.14'\n",
    )

    def counting(path: str, token: str | None = None) -> Any:
        calls.append(path)
        return inner(path, token)

    monkeypatch.setattr(diag, "_gh_api", counting)
    report = diag.sweep(["owner/repo"], token="t", now="2026-08-23T00:00:00Z")

    assert report["held_count"] == 1
    # The review still resolved a last-healthy run, so it had the data it needed.
    assert report["held"][0]["review"]["verdict"] == "benign"
    history_pages = [p for p in calls if "/runs?per_page=100" in p]
    assert len(history_pages) == 1, (
        f"run history paginated {len(history_pages)} times for one held workflow; "
        f"the onset walk must hand its last-healthy run to the review: {history_pages}"
    )


def test_sweep_ignores_stale_held_siblings_after_an_approval(monkeypatch) -> None:
    """Approval is forward-looking, so leftover held runs are not a live block.

    Approving a run marks that workflow FILE VERSION trusted for FUTURE runs; it
    does not retroactively release runs already created. A burst of runs from one
    moment therefore leaves held siblings behind, and the newest by created_at can
    be one of them while the workflow is healthy for new events.

    Observed on agents-63-issue-intake, agents-capability-check and
    agents-decompose: the approved runs reached attempt 2 and executed while
    same-second siblings stayed at attempt 1 and action_required. Reporting those
    as held sends someone to click a button that changes nothing.
    """
    burst = "2026-08-23T04:11:08Z"
    runs = [
        _held_run(1400, burst),  # stale sibling, never approved
        {  # the one that was approved and ran
            "id": 1401,
            "conclusion": "skipped",
            "status": "completed",
            "event": "issues",
            "created_at": burst,
        },
        {
            "id": 1399,
            "conclusion": "success",
            "status": "completed",
            "event": "issues",
            "created_at": "2026-08-23T03:00:00Z",
        },
    ]
    monkeypatch.setattr(diag, "_gh_api", _sweep_stub(runs=runs, onset_pages=[runs]))

    report = diag.sweep(["owner/repo"], token="t", now="2026-08-23T06:00:00Z")

    assert report["held_count"] == 0, (
        "a held sibling of an approved run is not a live block; the file version "
        "is trusted and new events will execute"
    )


def test_sweep_still_reports_when_nothing_executed_at_or_after_the_hold(monkeypatch) -> None:
    """The converse: an older success must not excuse a newer hold."""
    runs = [
        _held_run(1500, "2026-08-23T05:00:00Z"),
        {
            "id": 1499,
            "conclusion": "success",
            "status": "completed",
            "event": "issues",
            "created_at": "2026-08-22T05:00:00Z",
        },
    ]
    monkeypatch.setattr(diag, "_gh_api", _sweep_stub(runs=runs, onset_pages=[runs]))

    report = diag.sweep(["owner/repo"], token="t", now="2026-08-23T06:00:00Z")

    assert report["held_count"] == 1


def test_script_runs_when_invoked_by_path_without_pythonpath() -> None:
    """The invocation CI actually uses must import cleanly.

    health-40 runs `python scripts/workflow_startup_failure_diagnostic.py --sweep`
    and docs/INTEGRATION_GUIDE.md documents the same file-path form. Running a
    file by path does NOT put the repo root on sys.path, so `from scripts import
    api_client` raised ModuleNotFoundError and the liveness job failed on every
    run - while every local check passed, because they were run with PYTHONPATH
    set or via `python -m`.

    The whole point of this module is to notice when a workflow stops executing.
    Shipping it in a form that cannot execute was the same class of defect, so
    this test exercises the real invocation with a clean environment rather than a
    convenient one.
    """
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "workflow_startup_failure_diagnostic.py"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(root),
        timeout=60,
    )

    assert "ModuleNotFoundError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    assert "--sweep" in result.stdout
