from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "label_rules_assert.py"
SPEC = importlib.util.spec_from_file_location("label_rules_assert", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
label_rules_assert = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(label_rules_assert)


def _write(path: Path, contents: str = "ok\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def test_parse_allowlist_trims_blank_lines_and_normalizes_backslashes() -> None:
    raw = "\n  docs\\labels.yml  \n\n\t.github\\labels-core.yml\t\n rules/keep.yml \n"

    assert label_rules_assert._parse_allowlist(raw) == [
        "docs/labels.yml",
        ".github/labels-core.yml",
        "rules/keep.yml",
    ]


def test_list_checkout_files_skips_directories_and_git_metadata(tmp_path: Path) -> None:
    checkout = tmp_path / "trusted-config"
    (checkout / "rules" / "empty-dir").mkdir(parents=True)
    _write(checkout / "rules" / "labels.yml")
    _write(checkout / ".git" / "config")
    _write(checkout / "nested" / ".git" / "HEAD")

    files = list(label_rules_assert._list_checkout_files(checkout))

    assert files == [("rules/labels.yml", checkout / "rules" / "labels.yml")]


def test_main_fails_for_empty_allowlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRUSTED_LABEL_RULE_PATHS", "\n  \n")

    assert label_rules_assert.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "TRUSTED_LABEL_RULE_PATHS must contain at least one entry" in captured.err


def test_main_fails_when_checkout_root_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRUSTED_LABEL_RULE_PATHS", "rules/labels.yml")

    assert label_rules_assert.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Expected checkout directory 'trusted-config' not found" in captured.err


def test_main_fails_when_allowlisted_files_are_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRUSTED_LABEL_RULE_PATHS", "rules/labels.yml\nrules/missing.yml")
    _write(tmp_path / "trusted-config" / "rules" / "labels.yml")

    assert label_rules_assert.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Missing allowlisted paths:" in captured.err
    assert "  - rules/missing.yml" in captured.err


def test_main_fails_when_checkout_has_unexpected_extra_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRUSTED_LABEL_RULE_PATHS", "rules/labels.yml")
    _write(tmp_path / "trusted-config" / "rules" / "labels.yml")
    _write(tmp_path / "trusted-config" / "extra.yml")

    assert label_rules_assert.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Unexpected files present after sparse checkout:" in captured.err
    assert "  - extra.yml" in captured.err


def test_main_succeeds_when_checkout_matches_allowlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRUSTED_LABEL_RULE_PATHS", "rules\\labels.yml")
    _write(tmp_path / "trusted-config" / "rules" / "labels.yml")
    _write(tmp_path / "trusted-config" / ".git" / "config")

    assert label_rules_assert.main() == 0

    captured = capsys.readouterr()
    assert captured.out == "[label-rules-assert] Sparse checkout contents verified.\n"
    assert captured.err == ""
