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
