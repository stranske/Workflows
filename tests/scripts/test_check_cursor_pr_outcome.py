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
                    {"repository_url": "https://github.com/repos/stranske/Example", "number": n}
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


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_full_window_requires_fourteen_elapsed_days(offset):
    now = START + timedelta(days=14, seconds=offset)
    result = audit.collect(FIX, now=now, api=GitHub())
    complete = offset >= 0
    assert result["status"] == ("clear_search" if complete else "pending")
    assert result["blocking"] == result["drainable"] == int(not complete)
    assert result["window_end"] == (START + timedelta(days=14)).isoformat()


@pytest.mark.parametrize("offset,status", [(-1, "regression"), (0, "regression"), (1, "pending")])
def test_partial_window_filters_same_day_prs_at_observation_time(offset, status):
    now = START + timedelta(days=3)
    candidate = pull(created=now + timedelta(seconds=offset))
    result = audit.collect(FIX, now=now, api=GitHub([candidate]))
    assert result["status"] == status
    assert len(result["matches"]) == int(status == "regression")
    assert result["blocking"] == result["drainable"] == 1


@pytest.mark.parametrize("age", [0, 3, 14, 20, 365])
def test_search_date_range_stops_at_observed_window_end(age):
    api = GitHub()
    now = START + timedelta(days=age)
    result = audit.collect(FIX, now=now, api=api)
    expected_end = min(now, START + timedelta(days=14))
    search = next(call for call in api.calls if call.startswith("search/"))
    query = parse_qs(urlsplit(search).query)["q"][0]
    assert f"created:{START.date()}..{expected_end.date()}" in query
    assert result["query"] == query


def test_late_collection_avoids_result_cap_from_prs_outside_the_window():
    api = GitHub()

    def busy_owner(endpoint):
        result = api(endpoint)
        if endpoint.startswith("search/"):
            query = parse_qs(urlsplit(endpoint).query)["q"][0]
            if f"created:{START.date()}..{(START + timedelta(days=14)).date()}" not in query:
                return {**result, "total_count": 1001}
        return result

    result = audit.collect(FIX, now=START + timedelta(days=365), api=busy_owner)
    assert result["status"] == "clear_search"
    assert result["searched_count"] == 0


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
    "last_branch,status",
    [("cursor/issue-12", "clear_search"), ("cursor/issue-12-slug", "regression")],
)
def test_search_reads_the_last_result_at_the_github_cap(last_branch, status):
    api = GitHub([pull("cursor/issue-12")] * 999 + [pull(last_branch)])
    result = audit.collect(FIX, now=START + timedelta(days=14), api=api)
    assert result["status"] == status
    assert result["searched_count"] == 1000
    searches = [parse_qs(urlsplit(call).query) for call in api.calls if call.startswith("search/")]
    assert [query["page"] for query in searches] == [[str(page)] for page in range(1, 11)]
    assert api.calls[-1] == "repos/stranske/Example/pulls/1000"
    assert len(result["matches"]) == int(status == "regression")


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


@pytest.mark.parametrize("failed_read", ["fix", "search", "pull"])
@pytest.mark.parametrize("payload", ["null", "[]", '"unexpected"', "false", "0", "{"])
def test_cli_rejects_invalid_successful_transport_responses(
    monkeypatch, capsys, failed_read, payload
):
    api = GitHub([pull()])
    collect = audit.collect
    failed_endpoint = {
        "fix": "repos/stranske/Workflows/pulls/4564",
        "search": "search/issues?",
        "pull": "repos/stranske/Example/pulls/1",
    }[failed_read]

    def run(command, **kwargs):
        endpoint = command[-1]
        result = api(endpoint)
        stdout = payload if endpoint.startswith(failed_endpoint) else json.dumps(result)
        return subprocess.CompletedProcess(command, 0, stdout=stdout)

    monkeypatch.setattr(audit.subprocess, "run", run)
    monkeypatch.setattr(
        audit,
        "collect",
        lambda fix_pr, **kwargs: collect(fix_pr, now=START + timedelta(days=14)),
    )
    assert audit.main(["--fix-pr", FIX]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "unknown"
    assert result["blocking"] == result["drainable"] == 1
    assert api.calls[-1].startswith(failed_endpoint)
    assert len(api.calls) == {"fix": 1, "search": 2, "pull": 3}[failed_read]


@pytest.mark.parametrize("value", ["2026-11-09T12:00:00", "invalid", None])
def test_missing_or_invalid_timezone_cannot_establish_a_window(value):
    with pytest.raises(ValueError):
        audit.timestamp(value)


def test_excluded_repository_is_not_read_or_reported():
    api = GitHub([pull()])

    def excluded(endpoint):
        result = api(endpoint)
        if endpoint.startswith("search/"):
            result["items"][0]["repository_url"] = "https://github.com/repos/STRANSKE/Collab-Admin"
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
    assert result == {
        "status": "unknown",
        "reason": "GitHub evidence unavailable or incomplete",
        "blocking": 1,
        "drainable": 1,
    }


@pytest.mark.parametrize("status,code", [("clear_search", 0), ("regression", 1), ("pending", 2)])
def test_cli_exit_codes(monkeypatch, capsys, status, code):
    monkeypatch.setattr(audit, "collect", lambda *a, **kw: {"status": status})
    assert audit.main(["--fix-pr", FIX]) == code
    assert json.loads(capsys.readouterr().out)["status"] == status


@pytest.mark.parametrize(
    "age,candidates,truncated,expected",
    [
        (1, [], False, 2),
        (14, [pull()], False, 1),
        (14, [pull("cursor/issue-12")], False, 0),
        (14, [], False, 0),
        (14, [], True, 2),
    ],
)
def test_cli_search_outcomes_with_fake_api(
    monkeypatch, capsys, age, candidates, truncated, expected
):
    api = GitHub(candidates)
    collect = audit.collect

    def fake_api(endpoint):
        result = api(endpoint)
        if truncated and endpoint.startswith("search/"):
            result["incomplete_results"] = True
        return result

    monkeypatch.setattr(
        audit,
        "collect",
        lambda fix_pr, **kwargs: collect(fix_pr, now=START + timedelta(days=age), api=fake_api),
    )
    assert audit.main(["--fix-pr", FIX]) == expected
    result = json.loads(capsys.readouterr().out)
    assert result["blocking"] == int(expected != 0)
    assert result["drainable"] == int(expected != 0)
    if expected == 0:
        assert result["status"] == "clear_search"


@pytest.mark.parametrize("failed_read", ["second-page", "last-pull"])
@pytest.mark.parametrize("failure", ["timeout", "api-error", "invalid-json"])
def test_cli_cannot_clear_a_window_after_a_late_read_failure(
    monkeypatch, capsys, failed_read, failure
):
    # The first 100 PRs look clear. The only regression is on the final page,
    # so accepting evidence collected before the failed read would hide it.
    api = GitHub([pull("cursor/issue-12")] * 100 + [pull()])
    collect = audit.collect
    failed_endpoint = (
        "page=2" if failed_read == "second-page" else "repos/stranske/Example/pulls/101"
    )

    def interrupted(endpoint):
        result = api(endpoint)
        if failed_endpoint in endpoint:
            if failure == "timeout":
                raise subprocess.TimeoutExpired(["gh", "api"], 60)
            if failure == "api-error":
                raise subprocess.CalledProcessError(1, ["gh", "api"])
            raise json.JSONDecodeError("incomplete response", "", 0)
        return result

    monkeypatch.setattr(
        audit,
        "collect",
        lambda fix_pr, **kwargs: collect(fix_pr, now=START + timedelta(days=14), api=interrupted),
    )
    assert audit.main(["--fix-pr", FIX]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "unknown"
    assert result["blocking"] == result["drainable"] == 1
    assert api.calls[-1].endswith(failed_endpoint)
    assert len([call for call in api.calls if "/Example/pulls/" in call]) == (
        100 if failed_read == "second-page" else 101
    )
