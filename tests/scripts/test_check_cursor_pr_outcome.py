"""Production search evidence must not turn an empty partial search into acceptance."""

import json
import subprocess
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from scripts import check_cursor_pr_outcome as audit

START = datetime(2026, 11, 9, 12, tzinfo=UTC)
FIX = "stranske/Workflows#4564"


def pull(branch="cursor/issue-12-a-slug", *, created=None, author="github-actions[bot]"):
    return {
        "head": {"ref": branch},
        "created_at": (created or START).isoformat(),
        "user": {"login": author},
        "html_url": "https://github.com/stranske/Example/pull/12",
        "state": "closed",  # Closed orphan PRs still count as regressions.
    }


class GitHub:
    def __init__(self, pulls=(), *, merged=True):
        self.pulls = list(pulls)
        self.merged = merged
        self.calls = []

    def __call__(self, endpoint):
        self.calls.append(endpoint)
        if endpoint == "repos/stranske/Workflows/pulls/4564":
            return {"merged_at": START.isoformat() if self.merged else None}
        if endpoint.startswith("search/issues?"):
            query = parse_qs(urlsplit(endpoint).query)
            assert query["per_page"] == ["100"]
            assert "author:app/github-actions" in query["q"][0]
            assert "-repo:stranske/collab-admin" in query["q"][0]
            # Head names must be checked from pulls.get, never from PR prose.
            assert "head:" not in query["q"][0]
            offset = (int(query["page"][0]) - 1) * 100
            return {
                "incomplete_results": False,
                "total_count": len(self.pulls),
                "items": [
                    {"repository_url": "https://api.github.com/repos/stranske/Example", "number": n}
                    for n in range(offset + 1, min(offset + 100, len(self.pulls)) + 1)
                ],
            }
        return self.pulls[int(endpoint.rsplit("/", 1)[1]) - 1]


def test_unmerged_fix_cannot_start_observation():
    api = GitHub(merged=False)
    result = audit.collect(FIX, now=START, api=api)
    assert result["status"] == "pending"
    assert result["reason"] == "fix PR has not merged"
    assert api.calls == ["repos/stranske/Workflows/pulls/4564"]


@pytest.mark.parametrize("age,status", [(0, "pending"), (13, "pending"), (14, "clear_search")])
def test_empty_search_only_clears_a_complete_window(age, status):
    result = audit.collect(FIX, now=START + timedelta(days=age), api=GitHub())
    assert result["status"] == status
    assert result["searched_count"] == 0
    assert result["matches"] == []
    assert "search alone is not acceptance" in result["mid_run_merge_verification"]


@pytest.mark.parametrize("age", [0, 3, 14, 20])
def test_actual_slug_branch_including_closed_pr_is_a_regression(age):
    result = audit.collect(FIX, now=START + timedelta(days=age), api=GitHub([pull()]))
    assert result["status"] == "regression"
    assert result["matches"] == [
        {
            "url": "https://github.com/stranske/Example/pull/12",
            "branch": "cursor/issue-12-a-slug",
            "created_at": START.isoformat(),
        }
    ]


@pytest.mark.parametrize(
    "candidate",
    [
        pull("cursor/issue-12"),
        pull("cursor/issue-12-"),
        pull("codex/issue-12-slug"),
        pull(author="someone-else"),
        pull(created=START - timedelta(seconds=1)),
        pull(created=START + timedelta(days=14, seconds=1)),
    ],
)
def test_search_hits_require_exact_head_author_and_timestamps(candidate):
    result = audit.collect(FIX, now=START + timedelta(days=20), api=GitHub([candidate]))
    assert result["status"] == "clear_search"
    assert result["matches"] == []


def test_inclusive_end_boundary_and_mixed_case_slug():
    candidate = pull("cursor/issue-12-Fix_slug", created=START + timedelta(days=14))
    assert (
        audit.collect(FIX, now=START + timedelta(days=20), api=GitHub([candidate]))["status"]
        == "regression"
    )


def test_search_pages_are_all_read_before_reporting_no_matches():
    api = GitHub([pull("cursor/issue-12")] * 100 + [pull()])
    result = audit.collect(FIX, now=START + timedelta(days=14), api=api)
    assert result["status"] == "regression"
    assert result["searched_count"] == 101
    assert len([call for call in api.calls if call.startswith("search/")]) == 2


@pytest.mark.parametrize(
    "patch",
    [
        {"incomplete_results": True},
        {"total_count": 1001},
        {"total_count": 1, "items": []},
        {"total_count": -1},
        {"total_count": "0"},
    ],
)
def test_partial_or_capped_search_is_unknown(patch):
    api = GitHub()

    def incomplete(endpoint):
        result = api(endpoint)
        return {**result, **patch} if endpoint.startswith("search/") else result

    with pytest.raises(ValueError):
        audit.collect(FIX, now=START + timedelta(days=14), api=incomplete)


def test_changed_search_total_is_unknown():
    api = GitHub([pull("cursor/issue-12")] * 101)

    def changing(endpoint):
        result = api(endpoint)
        if "page=2" in endpoint:
            result["total_count"] = 102
        return result

    with pytest.raises(ValueError, match="changed during pagination"):
        audit.collect(FIX, now=START + timedelta(days=14), api=changing)


def test_duplicate_results_cannot_hide_an_unread_pr():
    api = GitHub([pull("cursor/issue-12")] * 100 + [pull()])

    def duplicate(endpoint):
        result = api(endpoint)
        if "page=2" in endpoint:
            result["items"][0]["number"] = 1
        return result

    with pytest.raises(ValueError, match="repeated a PR"):
        audit.collect(FIX, now=START + timedelta(days=14), api=duplicate)


def test_transport_uses_only_get_and_parses_json(monkeypatch):
    def run(command, **kwargs):
        assert command == ["gh", "api", "--method", "GET", "repos/stranske/Example/pulls/12"]
        assert kwargs == {"capture_output": True, "text": True, "timeout": 60, "check": True}
        return subprocess.CompletedProcess(command, 0, stdout='{"merged_at": null}')

    monkeypatch.setattr(audit.subprocess, "run", run)
    assert audit.gh_json("repos/stranske/Example/pulls/12") == {"merged_at": None}


@pytest.mark.parametrize("value", ["2026-11-09T12:00:00", "invalid", None])
def test_missing_or_invalid_timezone_cannot_establish_a_window(value):
    with pytest.raises(ValueError):
        audit.timestamp(value)


def test_excluded_repository_is_not_read_or_reported():
    api = GitHub([pull()])

    def excluded(endpoint):
        result = api(endpoint)
        if endpoint.startswith("search/"):
            result["items"][0][
                "repository_url"
            ] = "https://api.github.com/repos/STRANSKE/Collab-Admin"
        return result

    result = audit.collect(FIX, now=START + timedelta(days=14), api=excluded)
    assert result["status"] == "clear_search"
    assert result["matches"] == []
    assert not any("Example/pulls" in call or "Collab-Admin/pulls" in call for call in api.calls)


@pytest.mark.parametrize("fix", ["--help", "stranske/Workflows#0", "stranske/Collab-Admin#1"])
def test_invalid_or_excluded_fix_is_rejected_before_any_api_read(fix):
    api = GitHub()
    with pytest.raises(ValueError):
        audit.collect(fix, now=START, api=api)
    assert api.calls == []


def test_cli_failure_never_becomes_an_empty_success(monkeypatch, capsys):
    def unavailable(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["gh"], stderr="private diagnostic")

    monkeypatch.setattr(audit, "collect", unavailable)
    assert audit.main(["--fix-pr", FIX]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result == {"status": "unknown", "reason": "GitHub evidence unavailable or incomplete"}


@pytest.mark.parametrize("status,code", [("clear_search", 0), ("regression", 1), ("pending", 2)])
def test_cli_exit_codes(monkeypatch, capsys, status, code):
    monkeypatch.setattr(audit, "collect", lambda *a, **kw: {"status": status})
    assert audit.main(["--fix-pr", FIX]) == code
    assert json.loads(capsys.readouterr().out)["status"] == status


TARGET = "stranske/Example#12"


@pytest.fixture
def mid_run_api():
    """A merged target and a successful job whose push was skipped."""
    search = GitHub()
    target = {"merged_at": (START + timedelta(hours=1, minutes=5)).isoformat()}
    job = {
        "id": 91,
        "run_id": 42,
        "status": "completed",
        "conclusion": "success",
        "steps": [
            {
                "name": "Run Cursor",
                "number": 20,
                "status": "completed",
                "conclusion": "success",
                "started_at": (START + timedelta(hours=1)).isoformat(),
                "completed_at": (START + timedelta(hours=1, minutes=10)).isoformat(),
            },
            {
                "name": "Check target PR before pushing",
                "number": 21,
                "status": "completed",
                "conclusion": "success",
                "started_at": (START + timedelta(hours=1, minutes=10)).isoformat(),
                "completed_at": (START + timedelta(hours=1, minutes=11)).isoformat(),
            },
            {
                "name": "Commit and push changes",
                "number": 22,
                "status": "completed",
                "conclusion": "skipped",
            },
        ],
    }

    def api(endpoint):
        if endpoint == "repos/stranske/Example/pulls/12":
            return target
        if endpoint == "repos/stranske/Example/actions/jobs/91":
            return job
        return search(endpoint)

    return api, target, job


@pytest.mark.parametrize("age,status", [(2, "pending"), (14, "clear_search")])
def test_mid_run_evidence_records_timing_without_claiming_full_acceptance(mid_run_api, age, status):
    api, target, job = mid_run_api
    result = audit.collect(
        FIX, now=START + timedelta(days=age), api=api, target_pr=TARGET, job_id=91
    )
    assert result["status"] == status  # Candidate evidence cannot shorten the search window.
    evidence = result["mid_run_merge_verification"]
    assert evidence == {
        "status": "timing_verified",
        "target_pr": TARGET,
        "merged_at": target["merged_at"],
        "job_id": 91,
        "run_url": "https://github.com/stranske/Example/actions/runs/42",
        "cursor_started_at": job["steps"][0]["started_at"],
        "cursor_completed_at": job["steps"][0]["completed_at"],
        "guard_conclusion": "success",
        "push_conclusion": "skipped",
        "target_run_association": "required separately from the source-issue receipt",
        "next_target_verification": "required separately; this may not be the next matching run",
    }


def test_valid_event_does_not_clear_a_search_regression(mid_run_api):
    event_api, _, _ = mid_run_api
    search_api = GitHub([pull()])

    def api(endpoint):
        if endpoint.startswith("search/") or endpoint == "repos/stranske/Example/pulls/1":
            return search_api(endpoint)
        return event_api(endpoint)

    result = audit.collect(
        FIX, now=START + timedelta(days=14), api=api, target_pr=TARGET, job_id=91
    )
    assert result["status"] == "regression"
    assert len(result["matches"]) == 1
    assert result["mid_run_merge_verification"]["status"] == "timing_verified"


@pytest.mark.parametrize("minutes", [-1, 60, 70, 71, 14 * 24 * 60 + 1])
def test_merge_outside_cursor_or_at_ambiguous_boundaries_is_not_evidence(mid_run_api, minutes):
    api, target, _ = mid_run_api
    target["merged_at"] = (START + timedelta(minutes=minutes)).isoformat()
    with pytest.raises(ValueError, match="not demonstrably during Run Cursor"):
        audit.collect(FIX, now=START + timedelta(days=15), api=api, target_pr=TARGET, job_id=91)


@pytest.mark.parametrize(
    "patch",
    [
        {"id": 92},
        {"status": "in_progress"},
        {"conclusion": "failure"},
        {"run_id": None},
        {"run_id": True},
        {"run_id": -1},
    ],
)
def test_failed_unfinished_or_unidentified_job_is_not_evidence(mid_run_api, patch):
    api, _, job = mid_run_api
    job.update(patch)
    with pytest.raises(ValueError):
        audit.collect(FIX, now=START + timedelta(days=14), api=api, target_pr=TARGET, job_id=91)


@pytest.mark.parametrize(
    "index,patch",
    [
        (0, {"conclusion": "failure"}),
        (1, {"conclusion": "skipped"}),
        (2, {"conclusion": "success"}),
        (2, {"status": "in_progress"}),
        (1, {"number": 19}),
        (2, {"number": 21}),
        (0, {"number": True}),
        (0, {"completed_at": None}),
        (0, {"started_at": (START - timedelta(seconds=1)).isoformat()}),
        (1, {"started_at": (START + timedelta(minutes=69)).isoformat()}),
        (1, {"completed_at": (START + timedelta(days=15)).isoformat()}),
    ],
)
def test_bad_step_outcomes_order_or_timestamps_cannot_prove_skip(mid_run_api, index, patch):
    api, _, job = mid_run_api
    job["steps"][index].update(patch)
    with pytest.raises(ValueError):
        audit.collect(FIX, now=START + timedelta(days=14), api=api, target_pr=TARGET, job_id=91)


@pytest.mark.parametrize("duplicate", [False, True])
def test_missing_or_duplicate_guard_step_is_not_evidence(mid_run_api, duplicate):
    api, _, job = mid_run_api
    guard = job["steps"].pop(1)
    if duplicate:
        job["steps"].extend([guard, guard])
    with pytest.raises(ValueError, match="Missing or ambiguous"):
        audit.collect(FIX, now=START + timedelta(days=14), api=api, target_pr=TARGET, job_id=91)


@pytest.mark.parametrize(
    "target,job_id",
    [
        (TARGET, None),
        (None, 91),
        ("another/Example#12", 91),
        ("stranske/Collab-Admin#12", 91),
        ("stranske/Example#0", 91),
    ],
)
def test_invalid_event_scope_is_rejected_before_any_api_read(target, job_id):
    api = GitHub()
    with pytest.raises(ValueError):
        audit.collect(FIX, now=START, api=api, target_pr=target, job_id=job_id)
    assert api.calls == []


@pytest.mark.parametrize("job_id", [0, -1, True, "91"])
def test_invalid_job_id_is_rejected_before_reading_target(job_id):
    api = GitHub()
    with pytest.raises(ValueError, match="positive integer"):
        audit.collect_mid_run_merge(
            TARGET, job_id, start=START, end=START + timedelta(days=14), now=START, api=api
        )
    assert api.calls == []


def test_unmerged_fix_never_reads_candidate_event():
    api = GitHub(merged=False)
    result = audit.collect(FIX, now=START, api=api, target_pr=TARGET, job_id=91)
    assert result["status"] == "pending"
    assert api.calls == ["repos/stranske/Workflows/pulls/4564"]


def test_cli_passes_candidate_arguments_to_collector(monkeypatch, capsys):
    def collect(fix_pr, *, now, target_pr, job_id):
        assert (fix_pr, target_pr, job_id) == (FIX, TARGET, 91)
        assert now.tzinfo == UTC
        return {"status": "pending"}

    monkeypatch.setattr(audit, "collect", collect)
    assert audit.main(["--fix-pr", FIX, "--target-pr", TARGET, "--job-id", "91"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "pending"
