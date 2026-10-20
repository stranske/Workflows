from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import check_issue_consistency


def test_changed_headers_exclude_unchanged_base_merge_files(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "-b", "main")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Regression Test")
    (tmp_path / "base.txt").write_text("base\n")
    git("add", ".")
    git("commit", "-m", "initial")
    git("checkout", "-b", "repair")
    (tmp_path / "repair.py").write_text("value = 1\n")
    git("add", ".")
    git("commit", "-m", "fix: bounded repair")
    git("checkout", "main")
    (tmp_path / "CHANGELOG.md").write_text("* issue #11\n* issue #22\n")
    git("add", ".")
    git("commit", "-m", "release metadata")
    base = git("rev-parse", "HEAD")
    git("checkout", "repair")
    git("merge", "--no-edit", "main")
    monkeypatch.chdir(tmp_path)
    files, fallback = check_issue_consistency.collect_changed_files(None, base, "origin")
    assert files == [Path("repair.py")]
    assert fallback is False


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


def test_collect_header_issue_numbers_ignores_markdown_headings(tmp_path: Path) -> None:
    path = tmp_path / "sample.md"
    path.write_text("# Issue #1407\n\n<!-- Issue: 9999 -->\n", encoding="utf-8")
    numbers = check_issue_consistency.collect_header_issue_numbers(path, max_lines=5)
    assert numbers == {9999}


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


def test_is_release_context_recognizes_release_please_title() -> None:
    title = "chore(main): release 1.19.19"
    head_ref = "release-please--branches--main--components--workflows"

    assert check_issue_consistency.is_release_context(title, head_ref) is True
    assert check_issue_consistency.is_release_context(title, "manual/release") is False
    assert check_issue_consistency.is_release_context("fix: release parser", head_ref) is False


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
    assert (
        check_issue_consistency.should_scan_header_file(Path("docs/plans/SHORT_TERM_PLAN.md"))
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


def test_run_git_with_fallback_handles_bad_revision(monkeypatch) -> None:
    calls = []

    def fake_run_git(args: list[str]) -> str:
        calls.append(args)
        if args == ["log"]:
            raise RuntimeError("fatal: bad revision 'deadbeef..HEAD'")
        return "ok"

    monkeypatch.setattr(check_issue_consistency, "_run_git", fake_run_git)

    output, used_fallback = check_issue_consistency._run_git_with_fallback_and_flag(
        ["log"],
        ["log", "-n", "1"],
    )

    assert output == "ok"
    assert used_fallback is True
    assert calls == [["log"], ["log", "-n", "1"]]


def test_resolve_base_sha_prefers_merge_base(monkeypatch) -> None:
    calls = []

    def fake_is_ancestor(candidate: str, ref: str = "HEAD") -> bool:
        calls.append(("is_ancestor", candidate, ref))
        return False

    def fake_run_git(args: list[str]) -> str:
        calls.append(("run_git", args))
        assert args == ["merge-base", "deadbeef", "HEAD"]
        return "cafebabe\n"

    monkeypatch.setattr(check_issue_consistency, "_is_ancestor", fake_is_ancestor)
    monkeypatch.setattr(check_issue_consistency, "_run_git", fake_run_git)

    resolved = check_issue_consistency._resolve_base_sha_for_head("deadbeef")

    assert resolved == "cafebabe"
    assert calls[0] == ("is_ancestor", "deadbeef", "HEAD")


def test_resolve_base_sha_keeps_ancestor(monkeypatch) -> None:
    calls = []

    def fake_is_ancestor(candidate: str, ref: str = "HEAD") -> bool:
        calls.append(("is_ancestor", candidate, ref))
        return True

    def fake_run_git(args: list[str]) -> str:
        calls.append(("run_git", args))
        return "should-not-run"

    monkeypatch.setattr(check_issue_consistency, "_is_ancestor", fake_is_ancestor)
    monkeypatch.setattr(check_issue_consistency, "_run_git", fake_run_git)

    resolved = check_issue_consistency._resolve_base_sha_for_head("deadbeef")

    assert resolved == "deadbeef"
    assert calls == [("is_ancestor", "deadbeef", "HEAD")]


def test_collect_changed_files_uses_net_diff(monkeypatch) -> None:
    recorded = {}

    monkeypatch.setattr(
        check_issue_consistency,
        "_resolve_base_sha_for_head",
        lambda value: "deadbeef",
    )
    monkeypatch.setattr(
        check_issue_consistency,
        "_find_remote_with_ref",
        lambda *_args, **_kwargs: "upstream",
    )

    def fake_run_git_with_fallbacks_and_flag(primary: list[str], fallbacks: list[list[str]]):
        recorded["primary"] = primary
        recorded["fallbacks"] = fallbacks
        return ("src/a.py\nsrc/a.py\nsrc/b.py\n", False)

    monkeypatch.setattr(
        check_issue_consistency,
        "_run_git_with_fallbacks_and_flag",
        fake_run_git_with_fallbacks_and_flag,
    )

    files, used_fallback = check_issue_consistency.collect_changed_files(
        "main",
        "deadbeef",
        "upstream",
    )

    assert recorded["primary"] == [
        "diff",
        "--name-only",
        "deadbeef...HEAD",
    ]
    assert recorded["fallbacks"] == [
        ["diff", "--name-only", "upstream/main...HEAD"],
        ["log", "--format=", "--name-only", "--first-parent", "-n", "20"],
    ]
    assert files == [Path("src/a.py"), Path("src/b.py")]
    assert used_fallback is False


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


def test_main_skips_automated_release_before_issue_collection(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.setenv("PR_TITLE", "chore(main): release 1.19.19")
    monkeypatch.setenv("HEAD_REF", "release-please--branches--main--components--workflows")
    monkeypatch.setenv("BASE_REF", "main")
    monkeypatch.setenv("BASE_SHA", "deadbeef")
    monkeypatch.setenv("BASE_REMOTE", "origin")
    monkeypatch.setattr(sys, "argv", ["check_issue_consistency.py"])
    monkeypatch.setattr(
        check_issue_consistency,
        "collect_commit_messages",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("release PR must skip commit issue collection")
        ),
    )
    monkeypatch.setattr(
        check_issue_consistency,
        "collect_changed_files",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("release PR must skip header issue collection")
        ),
    )

    assert check_issue_consistency.main() == 0
    captured = capsys.readouterr()
    assert "Skipping issue consistency check: automated release PR." in captured.out


def test_main_autofix_title_hash_prefers_head_ref(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.setenv("PR_TITLE", "Autofix #1234")
    monkeypatch.setenv("HEAD_REF", "codex/issue-5678")
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
    assert "Issue consistency check passed for #5678." in captured.out


def test_main_title_hash_prefers_head_ref(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.setenv("PR_TITLE", "Update docs (#1234)")
    monkeypatch.setenv("HEAD_REF", "codex/issue-5678")
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
    assert "Issue consistency check passed for #5678." in captured.out


def test_main_title_hash_without_head_ref_issue_falls_back(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.setenv("PR_TITLE", "Update docs (#1234)")
    monkeypatch.setenv("HEAD_REF", "feature/no-issue")
    monkeypatch.setenv("BASE_REF", "")
    monkeypatch.setenv("BASE_SHA", "")
    monkeypatch.setenv("BASE_REMOTE", "origin")
    monkeypatch.setattr(sys, "argv", ["check_issue_consistency.py"])

    monkeypatch.setattr(
        check_issue_consistency,
        "collect_commit_messages",
        lambda *args, **kwargs: (["fix: resolve issue #5678"], False),
    )
    monkeypatch.setattr(
        check_issue_consistency,
        "collect_changed_files",
        lambda *args, **kwargs: ([], False),
    )

    assert check_issue_consistency.main() == 0
    captured = capsys.readouterr()
    assert "Issue consistency check passed for #5678." in captured.out


def test_main_autofix_skips_mismatched_commits(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.setenv("PR_TITLE", "Autofix #1234")
    monkeypatch.setenv("HEAD_REF", "codex/issue-5678")
    monkeypatch.setenv("BASE_REF", "")
    monkeypatch.setenv("BASE_SHA", "")
    monkeypatch.setenv("BASE_REMOTE", "origin")
    monkeypatch.setattr(sys, "argv", ["check_issue_consistency.py"])

    monkeypatch.setattr(
        check_issue_consistency,
        "collect_commit_messages",
        lambda *args, **kwargs: (["fix: issue 9999"], False),
    )
    monkeypatch.setattr(
        check_issue_consistency,
        "collect_changed_files",
        lambda *args, **kwargs: ([], False),
    )

    assert check_issue_consistency.main() == 0
    captured = capsys.readouterr()
    assert (
        "Skipping issue consistency check: autofix context with mismatched commit issues."
        in captured.out
    )


def test_main_autofix_skips_mismatched_headers(monkeypatch, capsys, tmp_path: Path) -> None:
    mismatch_file = tmp_path / "mismatch.py"
    mismatch_file.write_text("# Issue: 9999\n", encoding="utf-8")

    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.setenv("PR_TITLE", "Autofix #1234")
    monkeypatch.setenv("HEAD_REF", "codex/issue-5678")
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
        lambda *args, **kwargs: ([mismatch_file], False),
    )

    assert check_issue_consistency.main() == 0
    captured = capsys.readouterr()
    assert (
        "Skipping issue consistency check: autofix context with mismatched file headers."
        in captured.out
    )


def test_parsers_and_event_payloads_cover_empty_and_invalid_inputs(tmp_path: Path) -> None:
    invalid = tmp_path / "event.json"
    invalid.write_text("{", encoding="utf-8")

    assert check_issue_consistency._is_pr_marker_before_hash("") is False
    assert check_issue_consistency._is_ignored_commit_message("") is False
    assert check_issue_consistency.extract_title_issue_number("PR #12; issue-34") == 34
    assert check_issue_consistency.resolve_head_ref_issue_number("feature/no-issue") == (
        None,
        False,
    )
    assert check_issue_consistency.resolve_head_ref_issue_number("issue-1-issue-2") == (None, True)
    assert check_issue_consistency._load_event_payload(str(invalid)) == {}
    assert check_issue_consistency._extract_pull_request({"pull_requests": ["bad"]}) == {}


def test_event_context_handles_list_pull_requests_and_precedence(tmp_path: Path) -> None:
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "pull_requests": [
                    {"title": "Issue 21", "head": {"ref": "issue-21"}, "labels": ["auto fix"]}
                ],
                "workflow_run": {"head_branch": "ignored"},
            }
        ),
        encoding="utf-8",
    )
    assert check_issue_consistency._has_autofix_label(str(event)) is True
    assert check_issue_consistency.resolve_pr_context("existing", "", str(event)) == (
        "existing",
        "issue-21",
    )


def test_git_helpers_cover_failures_and_remote_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        check_issue_consistency, "_run_git", lambda _args: (_ for _ in ()).throw(RuntimeError("no"))
    )
    assert check_issue_consistency._remote_exists("") is False
    assert check_issue_consistency._remote_exists("origin") is False
    assert check_issue_consistency._resolve_base_remote("missing") == "missing"
    assert check_issue_consistency._resolve_base_sha_for_head(None) is None
    assert check_issue_consistency._resolve_base_sha_for_head("deadbeef") == "deadbeef"
    with __import__("pytest").raises(RuntimeError, match="no"):
        check_issue_consistency._run_git_with_fallback(["one"], None)


def test_collect_helpers_choose_each_non_sha_range(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(check_issue_consistency, "_resolve_base_sha_for_head", lambda value: value)
    monkeypatch.setattr(check_issue_consistency, "_find_remote_with_ref", lambda *_: None)
    monkeypatch.setattr(
        check_issue_consistency, "_run_git", lambda args: calls.append(args) or " fix: issue 9 \n\n"
    )

    assert check_issue_consistency.collect_commit_messages("main", None, "origin") == (
        ["fix: issue 9"],
        True,
    )
    assert check_issue_consistency.collect_changed_files(None, None, "origin") == (
        [Path("fix: issue 9")],
        True,
    )
    assert calls == [
        ["log", "--format=%s", "--first-parent", "-n", "20"],
        ["log", "--format=", "--name-only", "--first-parent", "-n", "20"],
    ]


def test_header_scan_handles_docstrings_and_unreadable_path(tmp_path: Path) -> None:
    source = tmp_path / "sample.py"
    source.write_text('"""\nIssue #41\nbody\n"""\nvalue = 1\n', encoding="utf-8")
    assert check_issue_consistency.collect_header_issue_numbers(source, 4) == {41}
    assert check_issue_consistency.collect_header_issue_numbers(tmp_path / "missing.py", 4) == set()


def test_fallback_helpers_try_all_candidates(monkeypatch) -> None:
    calls = []

    def fake_run(args):
        calls.append(args)
        if args != ["third"]:
            raise RuntimeError("bad revision")
        return "ok"

    monkeypatch.setattr(check_issue_consistency, "_run_git", fake_run)
    assert check_issue_consistency._run_git_with_fallbacks_and_flag(
        ["first"], [["second"], ["third"]]
    ) == ("ok", True)
    assert calls == [["first"], ["second"], ["third"]]
    with pytest.raises(RuntimeError, match="bad revision"):
        check_issue_consistency._run_git_with_fallbacks_and_flag(["first"], [])


def test_collect_helpers_cover_sha_and_remote_ranges(monkeypatch) -> None:
    monkeypatch.setattr(check_issue_consistency, "_resolve_base_sha_for_head", lambda _: "base")
    monkeypatch.setattr(check_issue_consistency, "_find_remote_with_ref", lambda *_: "origin")
    seen = {}

    def capture_log(primary, fallback):
        seen["log"] = (primary, fallback)
        return "issue #7\n", False

    def capture_diff(primary, fallbacks):
        seen["diff"] = (primary, fallbacks)
        return "a.py\nb.py\n", False

    monkeypatch.setattr(check_issue_consistency, "_run_git_with_fallback_and_flag", capture_log)
    monkeypatch.setattr(check_issue_consistency, "_run_git_with_fallbacks_and_flag", capture_diff)
    assert check_issue_consistency.collect_commit_messages("main", "base", "origin") == (
        ["issue #7"],
        False,
    )
    assert seen["log"] == (
        ["log", "--format=%s", "--first-parent", "base..HEAD"],
        ["log", "--format=%s", "--first-parent", "origin/main..HEAD"],
    )
    assert check_issue_consistency.collect_changed_files("main", "base", "origin") == (
        [Path("a.py"), Path("b.py")],
        False,
    )
    assert seen["diff"] == (
        ["diff", "--name-only", "base...HEAD"],
        [
            ["diff", "--name-only", "origin/main...HEAD"],
            ["log", "--format=", "--name-only", "--first-parent", "-n", "20"],
        ],
    )

    monkeypatch.setattr(check_issue_consistency, "_find_remote_with_ref", lambda *_: None)
    assert check_issue_consistency.collect_commit_messages("main", "base", "origin") == (
        ["issue #7"],
        False,
    )
    assert seen["log"] == (
        ["log", "--format=%s", "--first-parent", "base..HEAD"],
        ["log", "--format=%s", "--first-parent", "-n", "20"],
    )
    assert check_issue_consistency.collect_changed_files("main", "base", "origin") == (
        [Path("a.py"), Path("b.py")],
        False,
    )
    assert seen["diff"] == (
        ["diff", "--name-only", "base...HEAD"],
        [["log", "--format=", "--name-only", "--first-parent", "-n", "20"]],
    )


def test_main_reports_non_autofix_commit_and_header_mismatches(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.setenv("PR_TITLE", "Issue #10")
    monkeypatch.setenv("HEAD_REF", "issue-10")
    monkeypatch.setenv("BASE_REMOTE", "origin")
    monkeypatch.setattr(sys, "argv", ["check_issue_consistency.py"])
    monkeypatch.setattr(
        check_issue_consistency, "collect_commit_messages", lambda *_: (["issue #11"], False)
    )
    monkeypatch.setattr(check_issue_consistency, "collect_changed_files", lambda *_: ([], False))
    assert check_issue_consistency.main() == 1
    assert "do not match PR title" in capsys.readouterr().err

    header = tmp_path / "header.py"
    header.write_text("# Issue: 11\\n", encoding="utf-8")
    monkeypatch.setattr(check_issue_consistency, "collect_commit_messages", lambda *_: ([], False))
    monkeypatch.setattr(
        check_issue_consistency, "collect_changed_files", lambda *_: ([header], False)
    )
    assert check_issue_consistency.main() == 1
    assert "File headers reference issue numbers" in capsys.readouterr().err


def test_main_skips_unreliable_fallback_and_ambiguous_inference(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.setenv("PR_TITLE", "")
    monkeypatch.setenv("HEAD_REF", "feature/no-issue")
    monkeypatch.setenv("BASE_REMOTE", "origin")
    monkeypatch.setattr(sys, "argv", ["check_issue_consistency.py"])
    monkeypatch.setattr(
        check_issue_consistency, "collect_commit_messages", lambda *_: (["issue #10"], True)
    )
    monkeypatch.setattr(check_issue_consistency, "collect_changed_files", lambda *_: ([], True))
    assert check_issue_consistency.main() == 0
    assert "base reference unavailable" in capsys.readouterr().out

    monkeypatch.setattr(
        check_issue_consistency,
        "collect_commit_messages",
        lambda *_: (["issue #10", "issue #11"], False),
    )
    monkeypatch.setattr(check_issue_consistency, "collect_changed_files", lambda *_: ([], False))
    assert check_issue_consistency.main() == 1
    assert "Unable to determine issue number" in capsys.readouterr().err


def test_git_subprocess_adapters_and_remote_helpers(monkeypatch) -> None:
    class Result:
        def __init__(self, returncode, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    monkeypatch.setattr(
        check_issue_consistency.subprocess, "run", lambda *_a, **_k: Result(0, "ok")
    )
    assert check_issue_consistency._run_git(["status"]) == "ok"
    assert check_issue_consistency._is_ancestor("one") is True
    assert check_issue_consistency._remote_ref_exists("origin", "main") is True
    assert check_issue_consistency._find_remote_with_ref("missing", "main") == "missing"

    monkeypatch.setattr(
        check_issue_consistency.subprocess, "run", lambda *_a, **_k: Result(1, stderr="bad")
    )
    with pytest.raises(RuntimeError, match="bad"):
        check_issue_consistency._run_git(["status"])
    assert check_issue_consistency._is_ancestor("", "HEAD") is False
    assert check_issue_consistency._remote_ref_exists("", "main") is False


def test_header_scan_recognizes_comment_styles_and_exclusions(tmp_path: Path) -> None:
    source = tmp_path / "headers.txt"
    source.write_text("// issue-8\n/* Issue: 9 */\nvalue\n", encoding="utf-8")
    assert check_issue_consistency.collect_header_issue_numbers(source, 3) == {8, 9}
    assert check_issue_consistency.should_scan_header_file(None) is False


def test_main_skips_autofix_without_issue_and_reliable_fallback(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.setenv("PR_TITLE", "autofix")
    monkeypatch.setenv("HEAD_REF", "autofix/run")
    monkeypatch.setenv("BASE_REMOTE", "origin")
    monkeypatch.setattr(sys, "argv", ["check_issue_consistency.py"])
    assert check_issue_consistency.main() == 0
    assert "autofix context with no issue number" in capsys.readouterr().out

    monkeypatch.setenv("PR_TITLE", "Issue #10")
    monkeypatch.setenv("HEAD_REF", "issue-10")
    monkeypatch.setattr(check_issue_consistency, "collect_commit_messages", lambda *_: ([], True))
    monkeypatch.setattr(check_issue_consistency, "collect_changed_files", lambda *_: ([], False))
    assert check_issue_consistency.main() == 0
    assert "base reference unavailable" in capsys.readouterr().out


def test_event_payload_rejects_non_dict_and_empty_pull_request(tmp_path: Path) -> None:
    non_dict = tmp_path / "list.json"
    non_dict.write_text("[]", encoding="utf-8")
    assert check_issue_consistency._load_event_payload(str(non_dict)) == {}

    empty_pr = tmp_path / "empty-pr.json"
    empty_pr.write_text(json.dumps({"pull_request": {}}), encoding="utf-8")
    assert check_issue_consistency._has_autofix_label(str(empty_pr)) is False

    no_match = tmp_path / "labels.json"
    no_match.write_text(
        json.dumps({"pull_request": {"labels": [{"name": "enhancement"}, "docs"]}}),
        encoding="utf-8",
    )
    assert check_issue_consistency._has_autofix_label(str(no_match)) is False


def test_is_autofix_context_reads_event_path_from_env(tmp_path: Path, monkeypatch) -> None:
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps({"pull_request": {"labels": [{"name": "auto-fix"}]}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    assert check_issue_consistency.is_autofix_context("normal title", "feature/branch") is True
    assert (
        check_issue_consistency.is_autofix_context("normal title", "feature/branch", str(event))
        is True
    )


def test_resolve_pr_context_handles_non_dict_head_and_workflow_run(tmp_path: Path) -> None:
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "pull_request": {"title": "From event", "head": "not-a-dict"},
                "workflow_run": {"head_branch": "workflow-head"},
            }
        ),
        encoding="utf-8",
    )
    assert check_issue_consistency.resolve_pr_context("", "", str(event)) == (
        "From event",
        "workflow-head",
    )

    non_dict_run = tmp_path / "workflow-non-dict.json"
    non_dict_run.write_text(
        json.dumps({"pull_request": {"title": "T"}, "workflow_run": "bad"}),
        encoding="utf-8",
    )
    assert check_issue_consistency.resolve_pr_context("", "", str(non_dict_run)) == ("T", "")


def test_resolve_base_remote_uses_origin_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        check_issue_consistency,
        "_remote_exists",
        lambda name: name == "origin",
    )
    assert check_issue_consistency._resolve_base_remote("missing") == "origin"


def test_find_remote_with_ref_returns_none_when_absent(monkeypatch) -> None:
    monkeypatch.setattr(check_issue_consistency, "_remote_ref_exists", lambda *_: False)
    assert check_issue_consistency._find_remote_with_ref("origin", "main") is None


def test_run_git_fallback_helpers_cover_success_and_hard_errors(monkeypatch) -> None:
    calls = []

    def fake_run(args):
        calls.append(args)
        if args == ["primary"]:
            raise RuntimeError("bad revision")
        if args == ["fallback"]:
            return "from-fallback"
        if args == ["hard"]:
            raise RuntimeError("permission denied")
        if args in (["second"], ["third"]):
            raise RuntimeError("unknown revision")
        raise RuntimeError("unexpected")

    monkeypatch.setattr(check_issue_consistency, "_run_git", fake_run)
    assert check_issue_consistency._run_git_with_fallback(["primary"], ["fallback"]) == (
        "from-fallback"
    )
    with pytest.raises(RuntimeError, match="permission denied"):
        check_issue_consistency._run_git_with_fallback_and_flag(["hard"], ["fallback"])
    with pytest.raises(RuntimeError, match="bad revision"):
        check_issue_consistency._run_git_with_fallbacks_and_flag(["primary"], [])
    with pytest.raises(RuntimeError, match="permission denied"):
        check_issue_consistency._run_git_with_fallbacks_and_flag(
            ["primary"], [["hard"], ["fallback"]]
        )
    with pytest.raises(RuntimeError, match="unknown revision"):
        check_issue_consistency._run_git_with_fallbacks_and_flag(
            ["primary"], [["second"], ["third"]]
        )
    assert calls == [
        ["primary"],
        ["fallback"],
        ["hard"],
        ["primary"],
        ["primary"],
        ["hard"],
        ["primary"],
        ["second"],
        ["third"],
    ]


def test_collect_commit_messages_covers_sha_without_remote_and_ref_only(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(check_issue_consistency, "_resolve_base_sha_for_head", lambda value: value)
    monkeypatch.setattr(check_issue_consistency, "_find_remote_with_ref", lambda *_: None)
    monkeypatch.setattr(
        check_issue_consistency,
        "_run_git_with_fallback_and_flag",
        lambda primary, fallback: calls.append((primary, fallback)) or ("issue #12\n", True),
    )
    assert check_issue_consistency.collect_commit_messages("main", "abc", "origin") == (
        ["issue #12"],
        True,
    )
    assert calls == [
        (
            ["log", "--format=%s", "--first-parent", "abc..HEAD"],
            ["log", "--format=%s", "--first-parent", "-n", "20"],
        )
    ]

    monkeypatch.setattr(check_issue_consistency, "_find_remote_with_ref", lambda *_: "origin")
    monkeypatch.setattr(
        check_issue_consistency,
        "_run_git",
        lambda args: "issue #13\n" if "origin/main..HEAD" in args else "",
    )
    assert check_issue_consistency.collect_commit_messages("main", None, "origin") == (
        ["issue #13"],
        False,
    )

    monkeypatch.setattr(check_issue_consistency, "_find_remote_with_ref", lambda *_: None)
    monkeypatch.setattr(check_issue_consistency, "_run_git", lambda _args: "issue #14\n")
    assert check_issue_consistency.collect_commit_messages(None, None, "origin") == (
        ["issue #14"],
        True,
    )

    seen = {}

    def capture_fallback(primary, fallback):
        seen["fallback"] = fallback
        return "issue #15\n", True

    monkeypatch.setattr(
        check_issue_consistency, "_run_git_with_fallback_and_flag", capture_fallback
    )
    assert check_issue_consistency.collect_commit_messages(None, "abc", "origin") == (
        ["issue #15"],
        True,
    )
    assert seen["fallback"] == ["log", "--format=%s", "--first-parent", "-n", "20"]


def test_collect_changed_files_covers_ref_only_paths(monkeypatch) -> None:
    monkeypatch.setattr(check_issue_consistency, "_resolve_base_sha_for_head", lambda value: value)
    monkeypatch.setattr(check_issue_consistency, "_find_remote_with_ref", lambda *_: "origin")
    monkeypatch.setattr(
        check_issue_consistency,
        "_run_git_with_fallbacks_and_flag",
        lambda primary, fallbacks: ("src/a.py\nsrc/a.py\n\n", False),
    )
    assert check_issue_consistency.collect_changed_files("main", None, "origin") == (
        [Path("src/a.py")],
        False,
    )

    monkeypatch.setattr(check_issue_consistency, "_find_remote_with_ref", lambda *_: None)
    monkeypatch.setattr(check_issue_consistency, "_run_git", lambda _args: "src/b.py\n")
    assert check_issue_consistency.collect_changed_files("main", None, "origin") == (
        [Path("src/b.py")],
        True,
    )


def test_header_scan_covers_multiline_docstring_and_comment_lines(tmp_path: Path) -> None:
    multiline = tmp_path / "multi.py"
    multiline.write_text('"""\nIssue #61\n"""\nvalue = 1\n', encoding="utf-8")
    assert check_issue_consistency.collect_header_issue_numbers(multiline, 5) == {61}

    single = tmp_path / "single.py"
    single.write_text('"""Issue #62"""\nvalue = 1\n', encoding="utf-8")
    assert check_issue_consistency.collect_header_issue_numbers(single, 3) == {62}

    commented = tmp_path / "commented.py"
    commented.write_text("# plain note\n# Issue #63\nvalue = 1\n", encoding="utf-8")
    assert check_issue_consistency.collect_header_issue_numbers(commented, 3) == {63}

    markdown = tmp_path / "notes.md"
    markdown.write_text("# Heading\n<!-- Issue #64 -->\n", encoding="utf-8")
    assert check_issue_consistency.collect_header_issue_numbers(markdown, 3) == {64}


def test_main_bare_hash_warns_on_mismatch_and_ambiguous_head(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.setenv("PR_TITLE", "Update docs (#1234)")
    monkeypatch.setenv("HEAD_REF", "codex/issue-5678")
    monkeypatch.setenv("BASE_REMOTE", "origin")
    monkeypatch.setattr(sys, "argv", ["check_issue_consistency.py"])
    monkeypatch.setattr(check_issue_consistency, "collect_commit_messages", lambda *_: ([], False))
    monkeypatch.setattr(check_issue_consistency, "collect_changed_files", lambda *_: ([], False))
    assert check_issue_consistency.main() == 0
    err = capsys.readouterr().err
    assert "using head ref issue number instead" in err

    monkeypatch.setenv("HEAD_REF", "codex/issue-1234")
    assert check_issue_consistency.main() == 0
    err = capsys.readouterr().err
    assert "using head ref issue number instead" not in err

    monkeypatch.setenv("HEAD_REF", "codex/issue-1-issue-2")
    assert check_issue_consistency.main() == 0
    err = capsys.readouterr().err
    assert "Multiple issue numbers detected in head ref" in err
    assert "retaining PR title issue reference" in err


def test_main_infers_issue_from_headers_and_skips_ambiguous_fallback(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.setenv("PR_TITLE", "")
    monkeypatch.setenv("HEAD_REF", "feature/no-issue")
    monkeypatch.setenv("BASE_REMOTE", "origin")
    monkeypatch.setattr(sys, "argv", ["check_issue_consistency.py"])

    header = tmp_path / "module.py"
    header.write_text("# Issue #77\n", encoding="utf-8")
    skipped_dir = tmp_path / "tests" / "ignored.py"
    skipped_dir.parent.mkdir()
    skipped_dir.write_text("# Issue #88\n", encoding="utf-8")
    missing = tmp_path / "gone.py"

    monkeypatch.setattr(check_issue_consistency, "collect_commit_messages", lambda *_: ([], False))
    monkeypatch.setattr(
        check_issue_consistency,
        "collect_changed_files",
        lambda *_: ([header, skipped_dir, missing], False),
    )
    assert check_issue_consistency.main() == 0
    assert "Issue consistency check passed for #77." in capsys.readouterr().out

    monkeypatch.setattr(
        check_issue_consistency,
        "collect_commit_messages",
        lambda *_: (["issue #10", "issue #11"], True),
    )
    monkeypatch.setattr(check_issue_consistency, "collect_changed_files", lambda *_: ([], True))
    assert check_issue_consistency.main() == 0
    assert "unable to determine issue number from PR title with fallback" in capsys.readouterr().out


def test_main_skips_missing_and_excluded_files_during_mismatch_scan(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.setenv("PR_TITLE", "Issue #90")
    monkeypatch.setenv("HEAD_REF", "issue-90")
    monkeypatch.setenv("BASE_REMOTE", "origin")
    monkeypatch.setattr(sys, "argv", ["check_issue_consistency.py"])

    good = tmp_path / "good.py"
    good.write_text("# Issue #90\n", encoding="utf-8")
    excluded = tmp_path / ".github" / "workflow.yml"
    excluded.parent.mkdir()
    excluded.write_text("# Issue #91\n", encoding="utf-8")
    missing = tmp_path / "missing.py"

    monkeypatch.setattr(check_issue_consistency, "collect_commit_messages", lambda *_: ([], False))
    monkeypatch.setattr(
        check_issue_consistency,
        "collect_changed_files",
        lambda *_: ([good, excluded, missing], False),
    )
    assert check_issue_consistency.main() == 0
    assert "Issue consistency check passed for #90." in capsys.readouterr().out
