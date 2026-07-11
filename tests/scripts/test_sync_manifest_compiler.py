"""Tests for scripts/sync_manifest_compiler.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.sync_manifest_compiler import (
    COPY_SYNCED_SECTIONS,
    CompiledManifest,
    ManifestCompileError,
    ManifestEntry,
    RemovalEntry,
    SkipRepo,
    compile_manifest,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_manifest(tmp_path: Path, content: str) -> Path:
    p = tmp_path / ".github" / "sync-manifest.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Happy-path compilation
# ---------------------------------------------------------------------------


def test_compile_minimal_manifest(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        "version: 1\nworkflows:\n  - source: .github/workflows/autofix.yml\n    description: Autofix\n",
    )
    compiled = compile_manifest(path)
    assert compiled.version == 1
    assert len(compiled.section("workflows")) == 1
    entry = compiled.section("workflows")[0]
    assert entry.source == ".github/workflows/autofix.yml"
    assert entry.target == ".github/workflows/autofix.yml"
    assert entry.sync_mode is None
    assert entry.is_directory is False
    assert entry.template_sync is None
    assert entry.skip_repos == ()
    assert entry.overwrite_repos == ()
    assert entry.section == "workflows"


def test_compile_target_defaults_to_source(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        "version: 1\nscripts:\n  - source: scripts/foo.py\n    description: foo\n",
    )
    compiled = compile_manifest(path)
    assert compiled.section("scripts")[0].target == "scripts/foo.py"


def test_compile_explicit_target_overrides_source(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\nscripts:\n"
            "  - source: scripts/foo.py\n    target: scripts/bar.py\n    description: foo\n"
        ),
    )
    compiled = compile_manifest(path)
    assert compiled.section("scripts")[0].target == "scripts/bar.py"


def test_compile_create_only_sync_mode(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\nworkflows:\n"
            "  - source: .github/workflows/ci.yml\n"
            "    description: CI\n"
            "    sync_mode: create_only\n"
        ),
    )
    compiled = compile_manifest(path)
    assert compiled.section("workflows")[0].sync_mode == "create_only"


def test_compile_skip_repos_string_form(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\nworkflows:\n"
            "  - source: .github/workflows/autofix.yml\n"
            "    description: Autofix\n"
            "    skip_repos:\n"
            "      - owner/special\n"
        ),
    )
    compiled = compile_manifest(path)
    skip_repos = compiled.section("workflows")[0].skip_repos
    assert skip_repos == (SkipRepo(repo="owner/special", reason=""),)


def test_compile_skip_repos_dict_form_with_reason(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\nworkflows:\n"
            "  - source: .github/workflows/pr-00-gate.yml\n"
            "    description: Gate\n"
            "    skip_repos:\n"
            "      - repo: owner/custom\n"
            "        reason: Uses custom gate\n"
        ),
    )
    compiled = compile_manifest(path)
    skip_repos = compiled.section("workflows")[0].skip_repos
    assert skip_repos == (SkipRepo(repo="owner/custom", reason="Uses custom gate"),)


def test_compile_overwrite_repos(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\nworkflows:\n"
            "  - source: .github/workflows/ci.yml\n"
            "    description: CI\n"
            "    sync_mode: create_only\n"
            "    overwrite_repos:\n"
            "      - stranske/Template\n"
        ),
    )
    compiled = compile_manifest(path)
    assert compiled.section("workflows")[0].overwrite_repos == ("stranske/Template",)


def test_compile_is_directory(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\nscripts:\n"
            "  - source: scripts/langchain\n"
            "    description: LangChain helpers\n"
            "    is_directory: true\n"
        ),
    )
    compiled = compile_manifest(path)
    assert compiled.section("scripts")[0].is_directory is True


def test_compile_template_sync_exact(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\nscripts:\n"
            "  - source: scripts/aggregate_agent_metrics.py\n"
            "    description: Metrics\n"
            "    template_sync: exact\n"
        ),
    )
    compiled = compile_manifest(path)
    assert compiled.section("scripts")[0].template_sync == "exact"


def test_compile_removals(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\n"
            "workflows:\n"
            "  - source: .github/workflows/autofix.yml\n"
            "    description: Autofix\n"
            "removals:\n"
            "  - target: .github/workflows/old.yml\n"
            "    description: Removed stale workflow\n"
        ),
    )
    compiled = compile_manifest(path)
    assert len(compiled.removals) == 1
    assert compiled.removals[0] == RemovalEntry(
        target=".github/workflows/old.yml",
        description="Removed stale workflow",
    )


def test_compile_section_returns_empty_for_missing_section(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, "version: 1\nworkflows: []\n")
    compiled = compile_manifest(path)
    assert compiled.section("prompts") == ()
    assert compiled.section("nonexistent") == ()


def test_compile_all_entries_returns_flat_list(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\n"
            "workflows:\n"
            "  - source: .github/workflows/a.yml\n    description: A\n"
            "scripts:\n"
            "  - source: scripts/b.py\n    description: B\n"
        ),
    )
    compiled = compile_manifest(path)
    all_entries = compiled.all_entries()
    sources = {e.source for e in all_entries}
    assert sources == {".github/workflows/a.yml", "scripts/b.py"}


def test_compile_empty_manifest(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, "version: 1\n")
    compiled = compile_manifest(path)
    assert compiled.all_entries() == []
    assert compiled.removals == ()


def test_compile_null_manifest_treated_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "empty.yml"
    path.write_text("", encoding="utf-8")
    compiled = compile_manifest(path)
    assert compiled.all_entries() == []


def test_compile_multiple_sections(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\n"
            "workflows:\n"
            "  - source: .github/workflows/a.yml\n    description: A\n"
            "prompts:\n"
            "  - source: .github/codex/prompts/p.md\n    description: P\n"
            "scripts:\n"
            "  - source: scripts/s.py\n    description: S\n"
        ),
    )
    compiled = compile_manifest(path)
    assert len(compiled.section("workflows")) == 1
    assert len(compiled.section("prompts")) == 1
    assert len(compiled.section("scripts")) == 1


# ---------------------------------------------------------------------------
# Validation errors — invalid entries
# ---------------------------------------------------------------------------


def test_compile_raises_on_missing_source(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        "version: 1\nworkflows:\n  - description: Missing source\n",
    )
    with pytest.raises(ManifestCompileError) as exc_info:
        compile_manifest(path)
    assert any("source" in p for p in exc_info.value.problems)


def test_compile_raises_on_empty_source(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        "version: 1\nworkflows:\n  - source: ''\n    description: Empty\n",
    )
    with pytest.raises(ManifestCompileError) as exc_info:
        compile_manifest(path)
    assert any("source" in p for p in exc_info.value.problems)


def test_compile_raises_on_unknown_sync_mode(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\nworkflows:\n"
            "  - source: .github/workflows/a.yml\n"
            "    description: A\n"
            "    sync_mode: overwrite_always\n"
        ),
    )
    with pytest.raises(ManifestCompileError) as exc_info:
        compile_manifest(path)
    assert any("sync_mode" in p for p in exc_info.value.problems)


def test_compile_raises_on_skip_repos_not_a_list(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\nworkflows:\n"
            "  - source: .github/workflows/a.yml\n"
            "    description: A\n"
            "    skip_repos: owner/repo\n"
        ),
    )
    with pytest.raises(ManifestCompileError) as exc_info:
        compile_manifest(path)
    assert any("skip_repos" in p for p in exc_info.value.problems)


def test_compile_raises_on_skip_repos_dict_missing_repo_field(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\nworkflows:\n"
            "  - source: .github/workflows/a.yml\n"
            "    description: A\n"
            "    skip_repos:\n"
            "      - reason: No repo key here\n"
        ),
    )
    with pytest.raises(ManifestCompileError) as exc_info:
        compile_manifest(path)
    assert any("repo" in p for p in exc_info.value.problems)


def test_compile_raises_on_overwrite_repos_not_a_list(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\nworkflows:\n"
            "  - source: .github/workflows/a.yml\n"
            "    description: A\n"
            "    overwrite_repos: stranske/Template\n"
        ),
    )
    with pytest.raises(ManifestCompileError) as exc_info:
        compile_manifest(path)
    assert any("overwrite_repos" in p for p in exc_info.value.problems)


def test_compile_raises_on_unknown_template_sync_value(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\nscripts:\n"
            "  - source: scripts/foo.py\n"
            "    description: Foo\n"
            "    template_sync: copy\n"
        ),
    )
    with pytest.raises(ManifestCompileError) as exc_info:
        compile_manifest(path)
    assert any("template_sync" in p for p in exc_info.value.problems)


def test_compile_raises_on_is_directory_not_bool(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\nscripts:\n"
            "  - source: scripts/langchain\n"
            "    description: LangChain\n"
            "    is_directory: yes_it_is\n"
        ),
    )
    with pytest.raises(ManifestCompileError) as exc_info:
        compile_manifest(path)
    assert any("is_directory" in p for p in exc_info.value.problems)


def test_compile_raises_on_removal_missing_target(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        "version: 1\nremovals:\n  - description: No target here\n",
    )
    with pytest.raises(ManifestCompileError) as exc_info:
        compile_manifest(path)
    assert any("target" in p for p in exc_info.value.problems)


def test_compile_collects_all_problems(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\n"
            "workflows:\n"
            "  - description: Missing source\n"
            "  - source: .github/workflows/b.yml\n"
            "    description: B\n"
            "    sync_mode: bad_mode\n"
        ),
    )
    with pytest.raises(ManifestCompileError) as exc_info:
        compile_manifest(path)
    assert len(exc_info.value.problems) == 2


def test_compile_raises_file_not_found_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        compile_manifest(tmp_path / "does_not_exist.yml")


# ---------------------------------------------------------------------------
# skip_repos / overwrite_repos logic (directly on ManifestEntry)
# ---------------------------------------------------------------------------


def test_manifest_entry_skip_repos_string_form_has_empty_reason() -> None:
    entry = ManifestEntry(
        source="a.yml",
        target="a.yml",
        description="",
        sync_mode=None,
        skip_repos=(SkipRepo(repo="owner/repo", reason=""),),
        overwrite_repos=(),
        is_directory=False,
        template_sync=None,
        section="workflows",
    )
    skip = entry.skip_repos[0]
    assert skip.repo == "owner/repo"
    assert skip.reason == ""


def test_manifest_entry_is_frozen() -> None:
    entry = ManifestEntry(
        source="a.yml",
        target="a.yml",
        description="",
        sync_mode=None,
        skip_repos=(),
        overwrite_repos=(),
        is_directory=False,
        template_sync=None,
        section="workflows",
    )
    with pytest.raises(AttributeError):
        entry.source = "b.yml"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CLI --validate mode
# ---------------------------------------------------------------------------


def test_cli_validate_exits_zero_for_valid_manifest(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        "version: 1\nworkflows:\n  - source: .github/workflows/autofix.yml\n    description: A\n",
    )
    result = subprocess.run(
        [sys.executable, "scripts/sync_manifest_compiler.py", "--validate", str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "✅" in result.stdout


def test_cli_validate_exits_one_for_invalid_manifest(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        "version: 1\nworkflows:\n  - description: Missing source\n",
    )
    result = subprocess.run(
        [sys.executable, "scripts/sync_manifest_compiler.py", "--validate", str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "❌" in result.stderr


def test_cli_validate_exits_one_for_missing_file(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/sync_manifest_compiler.py",
            "--validate",
            str(tmp_path / "missing.yml"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1


def test_cli_validate_reports_problem_count(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path,
        (
            "version: 1\nworkflows:\n"
            "  - description: No source\n"
            "  - source: ''\n    description: Empty source\n"
        ),
    )
    result = subprocess.run(
        [sys.executable, "scripts/sync_manifest_compiler.py", "--validate", str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "2 manifest validation error" in result.stderr


# ---------------------------------------------------------------------------
# Compile against the real manifest (integration smoke test)
# ---------------------------------------------------------------------------


def test_compile_real_manifest_succeeds() -> None:
    real_path = Path(".github/sync-manifest.yml")
    if not real_path.exists():
        pytest.skip("Real manifest not found")
    compiled = compile_manifest(real_path)
    assert compiled.version == 1
    assert any(compiled.section(s) for s in COPY_SYNCED_SECTIONS)
    assert compiled.removals  # real manifest has at least one removal


def test_real_manifest_all_entries_have_non_empty_source() -> None:
    real_path = Path(".github/sync-manifest.yml")
    if not real_path.exists():
        pytest.skip("Real manifest not found")
    compiled = compile_manifest(real_path)
    for entry in compiled.all_entries():
        assert entry.source, f"Empty source in section {entry.section}"


def test_real_manifest_removals_have_non_empty_target() -> None:
    real_path = Path(".github/sync-manifest.yml")
    if not real_path.exists():
        pytest.skip("Real manifest not found")
    compiled = compile_manifest(real_path)
    for removal in compiled.removals:
        assert removal.target, "Empty target in removals"
