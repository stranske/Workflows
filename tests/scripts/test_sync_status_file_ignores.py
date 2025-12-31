from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

from scripts import sync_status_file_ignores


def _full_gitignore_content() -> str:
    return "\n".join(sync_status_file_ignores.CANONICAL_PATTERNS) + "\n"


def test_generate_minimal_block_includes_header_and_patterns() -> None:
    block = sync_status_file_ignores.generate_minimal_block()

    assert block.startswith(sync_status_file_ignores.GITIGNORE_BLOCK_HEADER.strip())
    assert block.endswith("\n")
    for pattern in sync_status_file_ignores.CANONICAL_PATTERNS:
        assert f"\n{pattern}\n" in block or block.endswith(f"{pattern}\n")


def test_check_gitignore_content_ignores_comments_and_negation() -> None:
    content = "\n".join(
        [
            "# comment",
            "codex-prompt.md",
            "!codex-output.md",
            "",
            "ci/autofix/history.json",
        ]
    )

    status = sync_status_file_ignores.check_gitignore_content(content)

    assert status["codex-prompt.md"] is True
    assert status["codex-output.md"] is False
    assert status["ci/autofix/history.json"] is True


def test_get_missing_patterns_returns_missing_only() -> None:
    content = "codex-prompt.md\nci/autofix/history.json\n"

    missing = sync_status_file_ignores.get_missing_patterns(content)

    assert "codex-prompt.md" not in missing
    assert "ci/autofix/history.json" not in missing
    assert "keepalive-metrics.ndjson" in missing


def test_generate_append_block_empty_is_blank() -> None:
    assert sync_status_file_ignores.generate_append_block([]) == ""


def test_print_check_report_missing_patterns(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = sync_status_file_ignores.print_check_report("codex-prompt.md\n", "demo")

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Missing" in captured.out
    assert "keepalive-metrics.ndjson" in captured.out


def test_print_check_report_all_present(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = sync_status_file_ignores.print_check_report(_full_gitignore_content(), "demo")

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "All canonical patterns present" in captured.out


def test_load_template_gitignore_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    original_exists = Path.exists

    def fake_exists(self: Path) -> bool:
        if self.name == ".gitignore" and "templates/consumer-repo" in str(self):
            return False
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)

    content = sync_status_file_ignores.load_template_gitignore()

    assert content == sync_status_file_ignores.generate_minimal_block()


def test_main_print_block(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["script", "--print-block"])

    exit_code = sync_status_file_ignores.main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == sync_status_file_ignores.load_template_gitignore() + "\n"


def test_main_print_patterns(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["script", "--print-patterns"])

    exit_code = sync_status_file_ignores.main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.splitlines() == sync_status_file_ignores.CANONICAL_PATTERNS


def test_main_gitignore_path_missing(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing_path = tmp_path / "missing.gitignore"
    monkeypatch.setattr(
        sys,
        "argv",
        ["script", "--gitignore-path", str(missing_path)],
    )

    exit_code = sync_status_file_ignores.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "not found" in captured.err


def test_main_gitignore_path_reports_missing(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gitignore_path = tmp_path / ".gitignore"
    gitignore_path.write_text("codex-prompt.md\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["script", "--gitignore-path", str(gitignore_path)],
    )

    exit_code = sync_status_file_ignores.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Missing" in captured.out


def test_main_check_local_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    gitignore_path = tmp_path / ".gitignore"
    gitignore_path.write_text(_full_gitignore_content(), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["script", "--check"])

    exit_code = sync_status_file_ignores.main()

    assert exit_code == 0


def test_main_repo_success(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    encoded = base64.b64encode(_full_gitignore_content().encode("utf-8")).decode("utf-8")

    class DummyResult:
        returncode = 0
        stdout = encoded
        stderr = ""

    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: DummyResult())
    monkeypatch.setattr(sys, "argv", ["script", "--repo", "owner/repo"])

    exit_code = sync_status_file_ignores.main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "All canonical patterns present" in captured.out
