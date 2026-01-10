from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts import api_client, cli_handler, duplicate_detection
from scripts.langchain import issue_dedup


class DummyResponse:
    def __init__(self, status_code: int, json_data=None, text: str = "") -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        if self._json_data is None:
            raise ValueError("No JSON")
        return self._json_data


def test_build_issue_payload_includes_optional_fields() -> None:
    payload = duplicate_detection.build_issue_payload(
        "Title",
        "Body",
        ["agents:dedup", "triage"],
    )

    assert payload == {
        "title": "Title",
        "body": "Body",
        "labels": ["agents:dedup", "triage"],
    }


def test_format_body_with_note_handles_empty_body() -> None:
    assert duplicate_detection.format_body_with_note(None, "Note") == "Note"
    assert duplicate_detection.format_body_with_note("", "Note") == "Note"


def test_format_body_with_note_appends_to_body() -> None:
    assert duplicate_detection.format_body_with_note("Body", "Note") == "Body\n\nNote"


def test_parse_source_issue_requires_number_and_title() -> None:
    with pytest.raises(ValueError):
        duplicate_detection.parse_source_issue({"title": "Missing number"})

    with pytest.raises(ValueError):
        duplicate_detection.parse_source_issue({"number": 3})


def test_build_duplicate_payload_uses_suffix_and_note() -> None:
    source = duplicate_detection.SourceIssue(
        number=42,
        title="Original",
        body="Details",
        url="http://example",
    )

    payload = duplicate_detection.build_duplicate_payload(
        source,
        title_suffix=" (dup)",
        note="Extra",
        labels=["agents:dedup"],
    )

    assert payload["title"] == "Original (dup)"
    assert payload["body"] == "Details\n\nExtra"
    assert payload["labels"] == ["agents:dedup"]


def test_select_issue_by_query_skips_prs_and_matches_body() -> None:
    issues = [
        {"number": 1, "title": "Other", "body": "Nope", "pull_request": {}},
        {"number": 2, "title": "", "body": "Target"},
        {"number": 3, "title": "Unrelated", "body": "Includes Target text"},
    ]

    match = duplicate_detection.select_issue_by_query(issues, "target")

    assert match is not None
    assert match.number == 3


def test_filter_issues_by_query_handles_empty_query() -> None:
    issues = [
        {"number": 1, "title": "Open issue", "body": ""},
        {"number": 2, "title": "PR", "body": "", "pull_request": {}},
        {"number": "bad", "title": "Missing numeric"},
    ]

    matches = duplicate_detection.filter_issues_by_query(issues, None)

    assert [match.number for match in matches] == [1]


def test_find_source_issue_scans_pages(monkeypatch) -> None:
    responses = [
        [{"number": 1, "title": "Nope", "body": ""}],
        [{"number": 2, "title": "Needle here", "body": ""}],
    ]

    def _fake_fetch(repo, token, *, labels, page, per_page=100):
        return responses.pop(0)

    monkeypatch.setattr(duplicate_detection.api_client, "fetch_issues", _fake_fetch)

    match = duplicate_detection.find_source_issue(
        "owner/repo",
        "token",
        query="needle",
        labels=None,
        pages=2,
    )

    assert match is not None
    assert match.number == 2


def test_collect_matching_issues_respects_limit(monkeypatch) -> None:
    responses = [
        [
            {"number": 1, "title": "Needle", "body": ""},
            {"number": 2, "title": "Needle again", "body": ""},
        ],
        [{"number": 3, "title": "Needle later", "body": ""}],
    ]

    def _fake_fetch(repo, token, *, labels, page, per_page=100):
        return responses.pop(0)

    monkeypatch.setattr(duplicate_detection.api_client, "fetch_issues", _fake_fetch)

    matches = duplicate_detection.collect_matching_issues(
        "owner/repo",
        "token",
        query="needle",
        labels=None,
        pages=2,
        limit=2,
    )

    assert [match.number for match in matches] == [1, 2]


def test_main_show_source_prints_issue(monkeypatch, capsys) -> None:
    def _fake_find(repo, token, *, query, labels, pages):
        return duplicate_detection.SourceIssue(
            number=7,
            title="Needle",
            body="Details",
            url="http://example/7",
        )

    monkeypatch.setattr(cli_handler, "find_source_issue", _fake_find)
    monkeypatch.setenv("ISSUE_DEDUP_SMOKE_ALLOWLIST", "owner/repo")
    monkeypatch.setenv("TEST_TOKEN", "token")

    result = cli_handler.main(
        [
            "--repo",
            "owner/repo",
            "--find-issue",
            "needle",
            "--show-source",
            "--token-env",
            "TEST_TOKEN",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "Source issue: #7 Needle (http://example/7)" in captured.out


def test_main_confirm_source_prints_confirmation(monkeypatch, capsys) -> None:
    def _fake_find(repo, token, *, query, labels, pages):
        return duplicate_detection.SourceIssue(
            number=8,
            title="Needle",
            body="Details",
            url="http://example/8",
        )

    monkeypatch.setattr(cli_handler, "find_source_issue", _fake_find)
    monkeypatch.setenv("ISSUE_DEDUP_SMOKE_ALLOWLIST", "owner/repo")
    monkeypatch.setenv("TEST_TOKEN", "token")

    result = cli_handler.main(
        [
            "--repo",
            "owner/repo",
            "--find-issue",
            "needle",
            "--confirm-source",
            "--token-env",
            "TEST_TOKEN",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "Source issue confirmed: #8 Needle (http://example/8)" in captured.out


def test_request_json_raises_on_error(monkeypatch) -> None:
    def _fake_request(method, url, headers=None, json=None, timeout=None):
        return DummyResponse(400, json_data={"message": "bad"})

    monkeypatch.setattr(api_client.requests, "request", _fake_request)

    with pytest.raises(RuntimeError, match="GitHub API error 400"):
        api_client._request_json("GET", "http://example", "token", payload=None)


def test_request_json_returns_payload(monkeypatch) -> None:
    def _fake_request(method, url, headers=None, json=None, timeout=None):
        return DummyResponse(200, json_data={"ok": True})

    monkeypatch.setattr(api_client.requests, "request", _fake_request)

    assert api_client._request_json("GET", "http://example", "token", None) == {"ok": True}


def test_request_json_retries_on_server_error(monkeypatch) -> None:
    responses = [
        DummyResponse(500, json_data={"message": "oops"}),
        DummyResponse(200, json_data={"ok": True}),
    ]

    def _fake_request(method, url, headers=None, json=None, timeout=None):
        return responses.pop(0)

    sleep_calls: list[float] = []

    monkeypatch.setattr(api_client.requests, "request", _fake_request)
    monkeypatch.setattr(api_client.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    assert api_client._request_json(
        "GET",
        "http://example",
        "token",
        None,
        max_attempts=2,
        backoff=0.5,
    ) == {"ok": True}
    assert sleep_calls == [0.5]


def test_request_json_retries_on_request_exception(monkeypatch) -> None:
    responses = [
        api_client.requests.RequestException("boom"),
        DummyResponse(200, json_data={"ok": True}),
    ]

    def _fake_request(method, url, headers=None, json=None, timeout=None):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    sleep_calls: list[float] = []

    monkeypatch.setattr(api_client.requests, "request", _fake_request)
    monkeypatch.setattr(api_client.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    assert api_client._request_json(
        "GET",
        "http://example",
        "token",
        None,
        max_attempts=2,
        backoff=0.25,
    ) == {"ok": True}
    assert sleep_calls == [0.25]


def test_find_dedup_comment_returns_match() -> None:
    comments = [
        {"body": "Nothing here"},
        {"body": f"{issue_dedup.SIMILAR_ISSUES_MARKER}\n- entry"},
    ]

    match = duplicate_detection.find_dedup_comment(comments)

    assert match is not None
    assert issue_dedup.SIMILAR_ISSUES_MARKER in match["body"]


def test_extract_similar_issue_refs_parses_links_and_numbers() -> None:
    body = "\n".join(
        [
            issue_dedup.SIMILAR_ISSUES_MARKER,
            "- [#12](http://example/12) - Title one (90% similar)",
            "- #34 - Another issue (82% similar)",
        ]
    )

    refs = duplicate_detection.extract_similar_issue_refs(body)

    assert [(ref.number, ref.url, ref.title) for ref in refs] == [
        (12, "http://example/12", "Title one"),
        (34, None, "Another issue"),
    ]


def test_format_duplicate_confirmation_prefers_issue_number() -> None:
    refs = [duplicate_detection.SimilarIssueRef(number=12, url="http://example/12", title=None)]

    assert duplicate_detection.format_duplicate_confirmation(refs) == (
        "Duplicate detected and linked to #12."
    )


def test_format_duplicate_confirmation_falls_back_to_generic_message() -> None:
    assert (
        duplicate_detection.format_duplicate_confirmation([])
        == "Duplicate detected and linked to similar issue(s)."
    )


def test_matches_expected_duplicate_number() -> None:
    refs = [duplicate_detection.SimilarIssueRef(number=12, url="http://example/12", title=None)]

    assert duplicate_detection.matches_expected_duplicate(
        refs,
        expected_number=12,
        expected_url=None,
    )
    assert not duplicate_detection.matches_expected_duplicate(
        refs,
        expected_number=99,
        expected_url=None,
    )


def test_matches_expected_duplicate_url_normalizes_trailing_slash() -> None:
    refs = [duplicate_detection.SimilarIssueRef(number=None, url="http://example/12/", title=None)]

    assert duplicate_detection.matches_expected_duplicate(
        refs,
        expected_number=None,
        expected_url="http://example/12",
    )


def test_main_check_issue_requires_expected_link(monkeypatch, capsys) -> None:
    comment_body = "\n".join(
        [
            issue_dedup.SIMILAR_ISSUES_MARKER,
            "- [#12](http://example/12) - Title one (90% similar)",
        ]
    )

    def _fake_check(repo, issue_number, token, *, attempts, interval):
        return {"body": comment_body, "html_url": "http://example/comment"}

    monkeypatch.setattr(cli_handler, "check_issue_for_duplicate", _fake_check)
    monkeypatch.setenv("ISSUE_DEDUP_SMOKE_ALLOWLIST", "owner/repo")
    monkeypatch.setenv("TEST_TOKEN", "token")

    result = cli_handler.main(
        [
            "--repo",
            "owner/repo",
            "--check-issue",
            "55",
            "--expected-issue-number",
            "99",
            "--token-env",
            "TEST_TOKEN",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "Expected duplicate link not found." in captured.err


def test_main_expected_link_requires_check_issue(monkeypatch, capsys) -> None:
    monkeypatch.setenv("ISSUE_DEDUP_SMOKE_ALLOWLIST", "owner/repo")
    monkeypatch.setenv("TEST_TOKEN", "token")

    result = cli_handler.main(
        [
            "--repo",
            "owner/repo",
            "--expected-issue-number",
            "99",
            "--token-env",
            "TEST_TOKEN",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "Expected issue match requires --check-issue." in captured.err


def test_main_requires_allowlist(monkeypatch, capsys) -> None:
    monkeypatch.delenv("ISSUE_DEDUP_SMOKE_ALLOWLIST", raising=False)
    monkeypatch.setenv("TEST_TOKEN", "token")

    result = cli_handler.main(
        [
            "--repo",
            "owner/repo",
            "--title",
            "Test",
            "--token-env",
            "TEST_TOKEN",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "Repository allowlist is empty" in captured.err


def test_main_rejects_repo_not_in_allowlist(monkeypatch, capsys) -> None:
    monkeypatch.setenv("ISSUE_DEDUP_SMOKE_ALLOWLIST", "owner/repo")
    monkeypatch.setenv("TEST_TOKEN", "token")

    result = cli_handler.main(
        [
            "--repo",
            "other/repo",
            "--title",
            "Test",
            "--token-env",
            "TEST_TOKEN",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "Repository other/repo is not in the allowlist." in captured.err


def test_main_prompts_before_creating_issue(monkeypatch, capsys) -> None:
    def _fake_create(repo, token, title, body, labels):
        raise AssertionError("create_issue should not be called when prompt declined")

    monkeypatch.setattr(api_client, "create_issue", _fake_create)
    monkeypatch.setenv("ISSUE_DEDUP_SMOKE_ALLOWLIST", "owner/repo")
    monkeypatch.setenv("TEST_TOKEN", "token")
    monkeypatch.setattr(cli_handler.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "n")

    result = cli_handler.main(
        [
            "--repo",
            "owner/repo",
            "--title",
            "Test",
            "--token-env",
            "TEST_TOKEN",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "Issue creation cancelled." in captured.err


def test_main_yes_skips_confirmation(monkeypatch) -> None:
    def _fake_create(repo, token, title, body, labels):
        return {"html_url": "http://example/created"}

    monkeypatch.setattr(api_client, "create_issue", _fake_create)
    monkeypatch.setenv("ISSUE_DEDUP_SMOKE_ALLOWLIST", "owner/repo")
    monkeypatch.setenv("TEST_TOKEN", "token")

    result = cli_handler.main(
        [
            "--repo",
            "owner/repo",
            "--title",
            "Test",
            "--token-env",
            "TEST_TOKEN",
            "--yes",
        ]
    )

    assert result == 0


def test_check_issue_for_duplicate_retries_until_found(monkeypatch) -> None:
    responses = [
        [{"body": "No marker yet"}],
        [{"body": f"Notice {issue_dedup.SIMILAR_ISSUES_MARKER} done", "html_url": "link"}],
    ]

    def _fake_fetch(repo, issue_number, token):
        return responses.pop(0)

    sleep_calls: list[float] = []

    monkeypatch.setattr(duplicate_detection.api_client, "fetch_issue_comments", _fake_fetch)
    monkeypatch.setattr(
        duplicate_detection.time, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    comment = duplicate_detection.check_issue_for_duplicate(
        "owner/repo",
        10,
        "token",
        attempts=2,
        interval=0.5,
    )

    assert comment is not None
    assert comment["html_url"] == "link"
    assert sleep_calls == [0.5]


def test_check_issue_for_no_duplicate_returns_true(monkeypatch) -> None:
    responses = [
        [{"body": "No marker yet"}],
        [{"body": "Still nothing"}],
    ]

    def _fake_fetch(repo, issue_number, token):
        return responses.pop(0)

    sleep_calls: list[float] = []

    monkeypatch.setattr(duplicate_detection.api_client, "fetch_issue_comments", _fake_fetch)
    monkeypatch.setattr(
        duplicate_detection.time, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    result = duplicate_detection.check_issue_for_no_duplicate(
        "owner/repo",
        12,
        "token",
        attempts=2,
        interval=0.25,
    )

    assert result is True
    assert sleep_calls == [0.25]


def test_check_issue_for_no_duplicate_returns_false_on_match(monkeypatch) -> None:
    responses = [
        [{"body": "No marker yet"}],
        [{"body": f"{issue_dedup.SIMILAR_ISSUES_MARKER} found"}],
    ]

    def _fake_fetch(repo, issue_number, token):
        return responses.pop(0)

    sleep_calls: list[float] = []

    monkeypatch.setattr(duplicate_detection.api_client, "fetch_issue_comments", _fake_fetch)
    monkeypatch.setattr(
        duplicate_detection.time, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    result = duplicate_detection.check_issue_for_no_duplicate(
        "owner/repo",
        12,
        "token",
        attempts=2,
        interval=0.25,
    )

    assert result is False
    assert sleep_calls == [0.25]
