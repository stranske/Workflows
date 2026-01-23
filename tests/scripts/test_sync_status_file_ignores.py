from __future__ import annotations

import base64
import runpy
import sys
from pathlib import Path

import pytest

from scripts import sync_status_file_ignores


def _full_gitignore_content() -> str:
    return "\n".join(sync_status_file_ignores.CANONICAL_PATTERNS) + "\n"


def _template_block_patterns() -> list[str]:
    template_path = Path(sync_status_file_ignores.__file__).resolve().parents[1]
    template_path = template_path / "templates/consumer-repo/.gitignore"
    text = template_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = next(
        idx
        for idx, line in enumerate(lines)
        if line.strip() == sync_status_file_ignores.PATTERN_BLOCK_BEGIN
    )
    end = next(
        idx
        for idx, line in enumerate(lines)
        if line.strip() == sync_status_file_ignores.PATTERN_BLOCK_END
    )
    patterns: list[str] = []
    for line in lines[start + 1 : end]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        patterns.append(stripped)
    return patterns


def test_generate_minimal_block_includes_header_and_patterns() -> None:
    block = sync_status_file_ignores.generate_minimal_block()

    assert block.startswith(sync_status_file_ignores.GITIGNORE_BLOCK_HEADER.strip())
    assert "Validate: python scripts/sync_status_file_ignores.py --check" in block
    assert sync_status_file_ignores.PATTERN_BLOCK_BEGIN in block
    assert sync_status_file_ignores.PATTERN_BLOCK_END in block
    assert block.endswith("\n")
    for pattern in sync_status_file_ignores.CANONICAL_PATTERNS:
        assert f"\n{pattern}\n" in block or block.endswith(f"{pattern}\n")


def test_canonical_patterns_cover_template_block() -> None:
    template_patterns = _template_block_patterns()
    missing = [
        pattern
        for pattern in template_patterns
        if pattern not in sync_status_file_ignores.CANONICAL_PATTERNS
    ]

    assert not missing, f"Missing canonical patterns: {missing}"


def test_load_template_patterns_matches_canonical() -> None:
    template_patterns = sync_status_file_ignores._load_template_patterns()

    assert template_patterns
    assert template_patterns == sync_status_file_ignores.CANONICAL_PATTERNS


def test_template_has_version_and_anchors() -> None:
    template_path = Path(sync_status_file_ignores.__file__).resolve().parents[1]
    template_path = template_path / "templates/consumer-repo/.gitignore"
    text = template_path.read_text(encoding="utf-8")

    assert sync_status_file_ignores.PATTERN_BLOCK_BEGIN in text
    assert sync_status_file_ignores.PATTERN_BLOCK_END in text
    assert sync_status_file_ignores.TEMPLATE_VERSION_PREFIX in text


def test_load_template_patterns_requires_version_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template_path = Path(sync_status_file_ignores.__file__).resolve().parents[1]
    template_path = template_path / "templates/consumer-repo/.gitignore"
    original_text = template_path.read_text(encoding="utf-8")
    modified_text = original_text.replace(sync_status_file_ignores.TEMPLATE_VERSION_PREFIX, "# ")
    original_read_text = Path.read_text

    def fake_read_text(self: Path, encoding: str = "utf-8") -> str:
        if self == template_path:
            return modified_text
        return original_read_text(self, encoding=encoding)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    assert sync_status_file_ignores._load_template_patterns() == []


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


def test_print_check_report_no_present(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = sync_status_file_ignores.print_check_report("", "demo")

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Present" not in captured.out
    assert "Missing" in captured.out


def test_load_template_gitignore_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    original_exists = Path.exists

    def fake_exists(self: Path) -> bool:
        if self.name == ".gitignore" and "templates/consumer-repo" in str(self):
            return False
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)

    content = sync_status_file_ignores.load_template_gitignore()

    assert content == sync_status_file_ignores.generate_minimal_block()


def test_load_template_block_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    original_exists = Path.exists

    def fake_exists(self: Path) -> bool:
        if self.name == ".gitignore" and "templates/consumer-repo" in str(self):
            return False
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)

    content = sync_status_file_ignores.load_template_block()

    assert content == sync_status_file_ignores.generate_minimal_block()


def test_load_template_block_uses_separator_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template_path = Path(sync_status_file_ignores.__file__).resolve().parents[1]
    template_path = template_path / "templates/consumer-repo/.gitignore"
    original_read_text = Path.read_text
    custom_text = "\n".join(
        [
            sync_status_file_ignores.SEPARATOR_LINE,
            "# Other Section",
            sync_status_file_ignores.SEPARATOR_LINE,
            "# junk",
            sync_status_file_ignores.SEPARATOR_LINE,
            "# Workflows Consumer Repo - Shared Status Files",
            sync_status_file_ignores.SEPARATOR_LINE,
            "# Auto-generated by workflows; causes merge conflicts if committed.",
            sync_status_file_ignores.SEPARATOR_LINE,
            "# Template-Version: 1",
            sync_status_file_ignores.PATTERN_BLOCK_BEGIN,
            "codex-prompt.md",
            sync_status_file_ignores.PATTERN_BLOCK_END,
            sync_status_file_ignores.SEPARATOR_LINE,
            "# Langchain Scripts Exclusion",
            sync_status_file_ignores.SEPARATOR_LINE,
        ]
    )

    def fake_read_text(self: Path, encoding: str = "utf-8") -> str:
        if self == template_path:
            return custom_text
        return original_read_text(self, encoding=encoding)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    block = sync_status_file_ignores.load_template_block()

    assert "# Workflows Consumer Repo - Shared Status Files" in block
    assert sync_status_file_ignores.PATTERN_BLOCK_END in block
    assert "Langchain Scripts Exclusion" not in block
    assert block.startswith(sync_status_file_ignores.SEPARATOR_LINE)
    assert block.endswith(f"{sync_status_file_ignores.PATTERN_BLOCK_END}\n")


def test_load_template_block_requires_end_separator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template_path = Path(sync_status_file_ignores.__file__).resolve().parents[1]
    template_path = template_path / "templates/consumer-repo/.gitignore"
    original_read_text = Path.read_text
    custom_text = "\n".join(
        [
            sync_status_file_ignores.SEPARATOR_LINE,
            "# Workflows Consumer Repo - Shared Status Files",
            sync_status_file_ignores.SEPARATOR_LINE,
            "# Template-Version: 1",
            sync_status_file_ignores.PATTERN_BLOCK_BEGIN,
            "codex-prompt.md",
            sync_status_file_ignores.PATTERN_BLOCK_END,
            "# Missing separator",
        ]
    )

    def fake_read_text(self: Path, encoding: str = "utf-8") -> str:
        if self == template_path:
            return custom_text
        return original_read_text(self, encoding=encoding)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    block = sync_status_file_ignores.load_template_block()

    assert block == sync_status_file_ignores.generate_minimal_block()


def test_load_template_block_requires_end_marker_after_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template_path = Path(sync_status_file_ignores.__file__).resolve().parents[1]
    template_path = template_path / "templates/consumer-repo/.gitignore"
    original_read_text = Path.read_text
    custom_text = "\n".join(
        [
            sync_status_file_ignores.SEPARATOR_LINE,
            "# Other Section",
            sync_status_file_ignores.PATTERN_BLOCK_BEGIN,
            "codex-prompt.md",
            sync_status_file_ignores.PATTERN_BLOCK_END,
            sync_status_file_ignores.SEPARATOR_LINE,
            "# Workflows Consumer Repo - Shared Status Files",
            sync_status_file_ignores.SEPARATOR_LINE,
            "# Template-Version: 1",
            sync_status_file_ignores.PATTERN_BLOCK_BEGIN,
            "codex-output.md",
            "# Missing end marker",
            sync_status_file_ignores.SEPARATOR_LINE,
        ]
    )

    def fake_read_text(self: Path, encoding: str = "utf-8") -> str:
        if self == template_path:
            return custom_text
        return original_read_text(self, encoding=encoding)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    block = sync_status_file_ignores.load_template_block()

    assert block == sync_status_file_ignores.generate_minimal_block()


def test_main_print_block(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["script", "--print-block"])

    exit_code = sync_status_file_ignores.main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == sync_status_file_ignores.load_template_block()


def test_main_print_patterns(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
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


def test_main_check_local_missing_gitignore(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["script", "--check"])

    exit_code = sync_status_file_ignores.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "No .gitignore found" in captured.err


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


def test_main_repo_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class DummyResult:
        returncode = 1
        stdout = ""
        stderr = "boom"

    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: DummyResult())
    monkeypatch.setattr(sys, "argv", ["script", "--repo", "owner/repo"])

    exit_code = sync_status_file_ignores.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error fetching .gitignore" in captured.err
    assert "boom" in captured.err


def test_main_repo_empty_response(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class DummyResult:
        returncode = 0
        stdout = ""
        stderr = ""

    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: DummyResult())
    monkeypatch.setattr(sys, "argv", ["script", "--repo", "owner/repo"])

    exit_code = sync_status_file_ignores.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "empty response" in captured.err


def test_main_repo_invalid_base64(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class DummyResult:
        returncode = 0
        stdout = "not-base64"
        stderr = ""

    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: DummyResult())
    monkeypatch.setattr(sys, "argv", ["script", "--repo", "owner/repo"])

    exit_code = sync_status_file_ignores.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error decoding .gitignore" in captured.err


def test_decode_repo_gitignore_strips_whitespace() -> None:
    encoded = base64.b64encode(_full_gitignore_content().encode("utf-8")).decode("utf-8")
    encoded = f"{encoded[:10]}\n{encoded[10:40]}\n{encoded[40:]}\n"

    decoded = sync_status_file_ignores.decode_repo_gitignore(encoded, "owner/repo")

    assert decoded == _full_gitignore_content()


def test_main_default_print_help(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["script"])

    exit_code = sync_status_file_ignores.main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "usage:" in captured.out


def test_module_main_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["script", "--print-patterns"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(Path(sync_status_file_ignores.__file__)), run_name="__main__")

    assert excinfo.value.code == 0
