from pathlib import Path

from scripts import check_gate_diff_quality


def test_literal_expected_assertion_detection() -> None:
    assert check_gate_diff_quality.has_literal_expected_assertion(
        'def test_value():\n    assert result == "expected"\n'
    )
    assert not check_gate_diff_quality.has_literal_expected_assertion(
        "def test_placeholder():\n    assert True\n"
    )


def test_scan_weak_test_files_flags_test_without_literal_assertion() -> None:
    assert check_gate_diff_quality.scan_weak_test_files(
        {
            "tests/test_placeholder.py": "def test_placeholder():\n    assert True\n",
            "docs/notes.py": "plain text without assertions\n",
        }
    ) == ["tests/test_placeholder.py"]


def test_secret_hits_scan_added_complete_diff_lines() -> None:
    github_token = "ghp_" + "A" * 24
    openai_token = "sk-" + "B" * 24
    diff = "\n".join(
        [
            "diff --git a/file b/file",
            f"+token = '{github_token}'",
            f"-old = '{openai_token}'",
        ]
    )

    assert check_gate_diff_quality.scan_secret_patterns(diff) == ["github-token"]


def test_scan_weak_test_files_accepts_literal_assertion() -> None:
    assert (
        check_gate_diff_quality.scan_weak_test_files(
            {"tests/test_real.py": 'def test_real():\n    assert output == "ok"\n'}
        )
        == []
    )


def test_weak_added_tests_keeps_filesystem_adapter(tmp_path, monkeypatch) -> None:
    test_file = tmp_path / "tests" / "test_real.py"
    test_file.parent.mkdir()
    test_file.write_text('def test_real():\n    assert output == "ok"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert check_gate_diff_quality._weak_added_tests([str(Path("tests/test_real.py"))]) == []


def test_secret_failure_message_reports_count_without_values(monkeypatch) -> None:
    github_token = "ghp_" + "A" * 24
    openai_token = "sk-" + "B" * 24
    monkeypatch.setattr(check_gate_diff_quality, "_changed_files", lambda _base, _head: [])
    monkeypatch.setattr(
        check_gate_diff_quality,
        "_full_diff",
        lambda _base, _head: "\n".join(
            [
                f"+token = '{github_token}'",
                f"+openai = '{openai_token}'",
            ]
        ),
    )

    failures = check_gate_diff_quality.check_diff_quality("base", "head")

    assert failures == [
        "secret-scan: complete diff contains 2 blocked secret pattern(s); "
        "inspect the diff and remove them"
    ]
    assert github_token not in failures[0]
    assert openai_token not in failures[0]
