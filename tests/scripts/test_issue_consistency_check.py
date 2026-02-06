from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import check_issue_consistency


def test_extract_issue_numbers_handles_word_and_slug() -> None:
    text = "Issue #1075 and issue-1075 are referenced."
    numbers = check_issue_consistency.extract_issue_numbers(text)
    assert numbers == {1075}


def test_extract_title_issue_number_prefers_hash() -> None:
    title = "Codex belt for #1075"
    assert check_issue_consistency.extract_title_issue_number(title) == 1075


def test_extract_title_issue_number_skips_autofix_pr_hash() -> None:
    title = "Auto-fix from CI failure (#1268)"
    assert check_issue_consistency.extract_title_issue_number(title) is None


def test_collect_header_issue_numbers_reads_issue_lines(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("# Issue: 1075\n# not an issue reference\n", encoding="utf-8")
    numbers = check_issue_consistency.collect_header_issue_numbers(path, max_lines=5)
    assert numbers == {1075}


def test_extract_issue_numbers_ignores_pr_hashes() -> None:
    text = "PR #1076 relates to Issue #1075"
    numbers = check_issue_consistency.extract_issue_numbers(text)
    assert numbers == {1075}


def test_extract_commit_issue_numbers_ignores_merge_and_ledger() -> None:
    messages = [
        "Merge pull request #1248 from stranske/codex/issue-1236",
        "Merge origin/main into codex/issue-1211",
        "chore(ledger): start task task-01 for issue #1211",
        "fix: resolve issue #1075 in parser",
    ]
    assert check_issue_consistency.extract_commit_issue_numbers(messages) == {1075}


def test_extract_head_ref_issue_numbers_from_branch() -> None:
    head_ref = "codex/issue-144-keepalive"
    numbers = check_issue_consistency.extract_head_ref_issue_numbers(head_ref)
    assert numbers == {144}


def test_extract_commit_issue_numbers_ignores_merge_commits() -> None:
    messages = [
        "Merge pull request #1248 from stranske/codex/issue-1236",
        "chore: resolve issue #1211",
    ]
    numbers = check_issue_consistency.extract_commit_issue_numbers(messages)
    assert numbers == {1211}


def test_is_ledger_file_detects_agents_ledgers() -> None:
    assert check_issue_consistency._is_ledger_file(Path(".agents/issue-123-ledger.yml")) is True
    assert check_issue_consistency._is_ledger_file(Path(".agents/.ledger-summary.md")) is True
    assert check_issue_consistency._is_ledger_file(Path("docs/issue-123-ledger.yml")) is False


def test_extract_commit_issue_numbers_keeps_merge_prefix_non_merge() -> None:
    messages = [
        "merge: resolve issue #1211",
        "fix: resolve issue #1212",
    ]
    numbers = check_issue_consistency.extract_commit_issue_numbers(messages)
    assert numbers == {1211, 1212}


def test_is_autofix_context_reads_event_labels(tmp_path: Path, monkeypatch) -> None:
    payload = {
        "pull_request": {
            "labels": [{"name": "auto-fix"}],
        }
    }
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    assert check_issue_consistency.is_autofix_context("", "") is True


def test_is_autofix_context_detects_hyphenated_title() -> None:
    assert check_issue_consistency.is_autofix_context("Auto-fix from CI failure", "") is True


def test_resolve_pr_context_reads_event_payload(tmp_path: Path) -> None:
    payload = {
        "pull_request": {
            "title": "Fix issue #4242",
            "head": {"ref": "codex/issue-4242"},
        }
    }
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(payload), encoding="utf-8")

    title, head_ref = check_issue_consistency.resolve_pr_context("", "", str(event_path))

    assert title == "Fix issue #4242"
    assert head_ref == "codex/issue-4242"


def test_resolve_pr_context_falls_back_to_workflow_run(tmp_path: Path) -> None:
    payload = {"workflow_run": {"head_branch": "autofix/ci-branch"}}
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(payload), encoding="utf-8")

    title, head_ref = check_issue_consistency.resolve_pr_context("", "", str(event_path))

    assert title == ""
    assert head_ref == "autofix/ci-branch"


def test_run_git_with_fallback_handles_ambiguous_argument(monkeypatch) -> None:
    calls = []

    def fake_run_git(args: list[str]) -> str:
        calls.append(args)
        if args == ["log"]:
            raise RuntimeError(
                "fatal: ambiguous argument 'deadbeef..HEAD': unknown revision or path not in the working tree."
            )
        return "ok"

    monkeypatch.setattr(check_issue_consistency, "_run_git", fake_run_git)

    output, used_fallback = check_issue_consistency._run_git_with_fallback_and_flag(
        ["log"],
        ["log", "-n", "1"],
    )

    assert output == "ok"
    assert used_fallback is True
    assert calls == [["log"], ["log", "-n", "1"]]


def test_should_scan_header_file_excludes_known_dirs() -> None:
    assert check_issue_consistency.should_scan_header_file(Path("src/app.py")) is True
    assert check_issue_consistency.should_scan_header_file(Path("agents/codex-101.md")) is False
    assert (
        check_issue_consistency.should_scan_header_file(Path(".agents/issue-101-ledger.yml"))
        is False
    )
    assert (
        check_issue_consistency.should_scan_header_file(
            Path(".github/workflows/agents-auto-pilot.yml")
        )
        is False
    )
    assert (
        check_issue_consistency.should_scan_header_file(Path("templates/consumer-repo/README.md"))
        is False
    )


def test_run_git_with_fallback_handles_invalid_object(monkeypatch) -> None:
    calls = []

    def fake_run_git(args: list[str]) -> str:
        calls.append(args)
        if args == ["log"]:
            raise RuntimeError("fatal: invalid object name 'deadbeef'.")
        return "ok"

    monkeypatch.setattr(check_issue_consistency, "_run_git", fake_run_git)

    output, used_fallback = check_issue_consistency._run_git_with_fallback_and_flag(
        ["log"],
        ["log", "-n", "1"],
    )

    assert output == "ok"
    assert used_fallback is True
    assert calls == [["log"], ["log", "-n", "1"]]


def test_main_skips_ambiguous_head_ref(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.setenv("PR_TITLE", "")
    monkeypatch.setenv("HEAD_REF", "codex/issue-101-issue-202")
    monkeypatch.setenv("BASE_REF", "")
    monkeypatch.setenv("BASE_SHA", "")
    monkeypatch.setenv("BASE_REMOTE", "origin")
    monkeypatch.setattr(sys, "argv", ["check_issue_consistency.py"])

    monkeypatch.setattr(
        check_issue_consistency,
        "collect_commit_messages",
        lambda *args, **kwargs: ([], False),
    )
    monkeypatch.setattr(
        check_issue_consistency,
        "collect_changed_files",
        lambda *args, **kwargs: ([], False),
    )

    assert check_issue_consistency.main() == 0
    captured = capsys.readouterr()
    assert "Skipping issue consistency check: no issue references found." in captured.out
