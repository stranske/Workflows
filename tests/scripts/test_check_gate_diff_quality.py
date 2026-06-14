from pathlib import Path

from scripts import check_gate_diff_quality


def test_literal_expected_assertion_detection() -> None:
    assert check_gate_diff_quality._has_literal_expected_assertion(
        'def test_value():\n    assert result == "expected"\n'
    )
    assert not check_gate_diff_quality._has_literal_expected_assertion(
        "def test_placeholder():\n    assert True\n"
    )


def test_weak_added_tests_flags_test_without_literal_assertion(tmp_path, monkeypatch) -> None:
    test_file = tmp_path / "tests" / "test_placeholder.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert check_gate_diff_quality._weak_added_tests(["tests/test_placeholder.py"]) == [
        "tests/test_placeholder.py"
    ]


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

    assert check_gate_diff_quality._secret_hits(diff) == ["github-token"]


def test_clean_fixture_is_not_weak(tmp_path, monkeypatch) -> None:
    test_file = tmp_path / "tests" / "test_real.py"
    test_file.parent.mkdir()
    test_file.write_text('def test_real():\n    assert output == "ok"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert check_gate_diff_quality._weak_added_tests([str(Path("tests/test_real.py"))]) == []
