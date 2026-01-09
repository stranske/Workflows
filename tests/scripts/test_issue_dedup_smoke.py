from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts import issue_dedup_smoke
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
    payload = issue_dedup_smoke.build_issue_payload(
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
    assert issue_dedup_smoke.format_body_with_note(None, "Note") == "Note"
    assert issue_dedup_smoke.format_body_with_note("", "Note") == "Note"


def test_format_body_with_note_appends_to_body() -> None:
    assert issue_dedup_smoke.format_body_with_note("Body", "Note") == "Body\n\nNote"


def test_parse_source_issue_requires_number_and_title() -> None:
    with pytest.raises(ValueError):
        issue_dedup_smoke.parse_source_issue({"title": "Missing number"})

    with pytest.raises(ValueError):
        issue_dedup_smoke.parse_source_issue({"number": 3})


def test_build_duplicate_payload_uses_suffix_and_note() -> None:
    source = issue_dedup_smoke.SourceIssue(
        number=42,
        title="Original",
        body="Details",
        url="http://example",
    )

    payload = issue_dedup_smoke.build_duplicate_payload(
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

    match = issue_dedup_smoke.select_issue_by_query(issues, "target")

    assert match is not None
    assert match.number == 3


def test_filter_issues_by_query_handles_empty_query() -> None:
    issues = [
        {"number": 1, "title": "Open issue", "body": ""},
        {"number": 2, "title": "PR", "body": "", "pull_request": {}},
        {"number": "bad", "title": "Missing numeric"},
    ]

    matches = issue_dedup_smoke.filter_issues_by_query(issues, None)

    assert [match.number for match in matches] == [1]


def test_find_source_issue_scans_pages(monkeypatch) -> None:
    responses = [
        [{"number": 1, "title": "Nope", "body": ""}],
        [{"number": 2, "title": "Needle here", "body": ""}],
    ]

    def _fake_fetch(repo, token, *, labels, page, per_page=100):
        return responses.pop(0)

    monkeypatch.setattr(issue_dedup_smoke, "fetch_issues", _fake_fetch)

    match = issue_dedup_smoke.find_source_issue(
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

    monkeypatch.setattr(issue_dedup_smoke, "fetch_issues", _fake_fetch)

    matches = issue_dedup_smoke.collect_matching_issues(
        "owner/repo",
        "token",
        query="needle",
        labels=None,
        pages=2,
        limit=2,
    )

    assert [match.number for match in matches] == [1, 2]


def test_request_json_raises_on_error(monkeypatch) -> None:
    def _fake_request(method, url, headers=None, json=None, timeout=None):
        return DummyResponse(400, json_data={"message": "bad"})

    monkeypatch.setattr(issue_dedup_smoke.requests, "request", _fake_request)

    with pytest.raises(RuntimeError, match="GitHub API error 400"):
        issue_dedup_smoke._request_json("GET", "http://example", "token", payload=None)


def test_request_json_returns_payload(monkeypatch) -> None:
    def _fake_request(method, url, headers=None, json=None, timeout=None):
        return DummyResponse(200, json_data={"ok": True})

    monkeypatch.setattr(issue_dedup_smoke.requests, "request", _fake_request)

    assert issue_dedup_smoke._request_json("GET", "http://example", "token", None) == {"ok": True}


def test_find_dedup_comment_returns_match() -> None:
    comments = [
        {"body": "Nothing here"},
        {"body": f"{issue_dedup.SIMILAR_ISSUES_MARKER}\n- entry"},
    ]

    match = issue_dedup_smoke.find_dedup_comment(comments)

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

    refs = issue_dedup_smoke.extract_similar_issue_refs(body)

    assert [(ref.number, ref.url, ref.title) for ref in refs] == [
        (12, "http://example/12", "Title one"),
        (34, None, "Another issue"),
    ]


def test_format_duplicate_confirmation_prefers_issue_number() -> None:
    refs = [issue_dedup_smoke.SimilarIssueRef(number=12, url="http://example/12", title=None)]

    assert issue_dedup_smoke.format_duplicate_confirmation(refs) == (
        "Duplicate detected and linked to #12."
    )


def test_format_duplicate_confirmation_falls_back_to_generic_message() -> None:
    assert (
        issue_dedup_smoke.format_duplicate_confirmation([])
        == "Duplicate detected and linked to similar issue(s)."
    )


def test_check_issue_for_duplicate_retries_until_found(monkeypatch) -> None:
    responses = [
        [{"body": "No marker yet"}],
        [{"body": f"Notice {issue_dedup.SIMILAR_ISSUES_MARKER} done", "html_url": "link"}],
    ]

    def _fake_fetch(repo, issue_number, token):
        return responses.pop(0)

    sleep_calls: list[float] = []

    monkeypatch.setattr(issue_dedup_smoke, "fetch_issue_comments", _fake_fetch)
    monkeypatch.setattr(
        issue_dedup_smoke.time, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    comment = issue_dedup_smoke.check_issue_for_duplicate(
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

    monkeypatch.setattr(issue_dedup_smoke, "fetch_issue_comments", _fake_fetch)
    monkeypatch.setattr(
        issue_dedup_smoke.time, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    result = issue_dedup_smoke.check_issue_for_no_duplicate(
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

    monkeypatch.setattr(issue_dedup_smoke, "fetch_issue_comments", _fake_fetch)
    monkeypatch.setattr(
        issue_dedup_smoke.time, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    result = issue_dedup_smoke.check_issue_for_no_duplicate(
        "owner/repo",
        12,
        "token",
        attempts=2,
        interval=0.25,
    )

    assert result is False
    assert sleep_calls == [0.25]
