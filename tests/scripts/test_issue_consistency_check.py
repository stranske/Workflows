from __future__ import annotations

import json
from pathlib import Path

from scripts import check_issue_consistency


def test_extract_issue_numbers_handles_word_and_slug() -> None:
    text = "Issue #1075 and issue-1075 are referenced."
    numbers = check_issue_consistency.extract_issue_numbers(text)
    assert numbers == {1075}


def test_extract_title_issue_number_prefers_hash() -> None:
    title = "Codex belt for #1075"
    assert check_issue_consistency.extract_title_issue_number(title) == 1075


def test_collect_header_issue_numbers_reads_issue_lines(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("# Issue: 1075\n# not an issue reference\n", encoding="utf-8")
    numbers = check_issue_consistency.collect_header_issue_numbers(path, max_lines=5)
    assert numbers == {1075}


def test_extract_issue_numbers_ignores_pr_hashes() -> None:
    text = "PR #1076 relates to Issue #1075"
    numbers = check_issue_consistency.extract_issue_numbers(text)
    assert numbers == {1075}


def test_extract_head_ref_issue_numbers_from_branch() -> None:
    head_ref = "codex/issue-144-keepalive"
    numbers = check_issue_consistency.extract_head_ref_issue_numbers(head_ref)
    assert numbers == {144}


def test_is_autofix_context_reads_event_labels(tmp_path: Path, monkeypatch) -> None:
    payload = {
        "pull_request": {
            "labels": [{"name": "autofix"}],
        }
    }
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    assert check_issue_consistency.is_autofix_context("", "") is True
