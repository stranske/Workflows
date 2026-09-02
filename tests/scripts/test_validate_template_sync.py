"""Tests for scripts/validate_template_sync.py"""

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import validate_template_sync as vts
from scripts.sync_manifest_compiler import compile_manifest


def create_test_structure(tmp_path: Path) -> tuple[Path, Path]:
    """Create temporary source and template directories."""
    source = tmp_path / ".github" / "scripts"
    template = tmp_path / "templates" / "consumer-repo" / ".github" / "scripts"
    source.mkdir(parents=True)
    template.mkdir(parents=True)

    # Copy validator and its dependency so they are importable when run from tmp_path
    script_dir = tmp_path / "scripts"
    script_dir.mkdir(parents=True)
    shutil.copy("scripts/validate_template_sync.py", script_dir / "validate_template_sync.py")
    shutil.copy("scripts/sync_manifest_compiler.py", script_dir / "sync_manifest_compiler.py")

    return source, template


def write_manifest(tmp_path: Path, script_names: list[str]) -> None:
    manifest_dir = tmp_path / ".github"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    entries = "\n".join(
        f"  - source: .github/scripts/{name}\n    description: test" for name in script_names
    )
    manifest = (
        f"version: 1\n\nscripts:\n{entries}\n" if script_names else "version: 1\nscripts: []\n"
    )
    (manifest_dir / "sync-manifest.yml").write_text(manifest, encoding="utf-8")


def write_raw_manifest(tmp_path: Path, manifest: str) -> None:
    manifest_dir = tmp_path / ".github"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "sync-manifest.yml").write_text(manifest, encoding="utf-8")


def test_validator_passes_when_files_match(tmp_path):
    """Validator should exit 0 when source and template files match."""
    source, template = create_test_structure(tmp_path)

    # Create matching files
    (source / "test.js").write_text("console.log('test');")
    (template / "test.js").write_text("console.log('test');")
    write_manifest(tmp_path, ["test.js"])

    result = subprocess.run(
        [sys.executable, "scripts/validate_template_sync.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "✅ All template files in sync" in result.stdout


def test_validator_fails_on_hash_mismatch(tmp_path):
    """Validator should exit 1 when files have different content."""
    source, template = create_test_structure(tmp_path)

    # Create mismatched files
    (source / "test.js").write_text("console.log('source');")
    (template / "test.js").write_text("console.log('template');")
    write_manifest(tmp_path, ["test.js"])

    result = subprocess.run(
        [sys.executable, "scripts/validate_template_sync.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "❌ Template files out of sync" in result.stdout
    assert "test.js" in result.stdout


def test_validator_fails_on_missing_template(tmp_path):
    """Validator should exit 1 when source file exists but template doesn't."""
    source, template = create_test_structure(tmp_path)

    # Create source file without template counterpart
    (source / "new_file.js").write_text("console.log('new');")
    write_manifest(tmp_path, ["new_file.js"])

    result = subprocess.run(
        [sys.executable, "scripts/validate_template_sync.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "❌ Template files out of sync" in result.stdout
    assert "new_file.js" in result.stdout
    assert "(MISSING - needs to be created)" in result.stdout


def test_validator_handles_missing_template_directory(tmp_path):
    """Validator should handle missing template directory gracefully."""
    source, _ = create_test_structure(tmp_path)

    # Remove template directory entirely
    shutil.rmtree(tmp_path / "templates")

    (source / "test.js").write_text("console.log('test');")
    write_manifest(tmp_path, ["test.js"])

    result = subprocess.run(
        [sys.executable, "scripts/validate_template_sync.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    # Should fail with clear error
    assert result.returncode == 1
    assert "Template directory not found" in result.stdout or "test.js" in result.stdout


def test_validator_suggests_sync_command(tmp_path):
    """Validator should suggest running sync script and staging changed template files."""
    source, template = create_test_structure(tmp_path)

    (source / "test.js").write_text("console.log('source');")
    (template / "test.js").write_text("console.log('template');")
    write_manifest(tmp_path, ["test.js"])

    result = subprocess.run(
        [sys.executable, "scripts/validate_template_sync.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "./scripts/sync_templates.sh" in result.stdout
    assert "git add templates/consumer-repo/.github/scripts/test.js" in result.stdout


def test_validator_handles_multiple_mismatches(tmp_path):
    """Validator should report all mismatched files."""
    source, template = create_test_structure(tmp_path)

    # Create multiple mismatches
    (source / "file1.js").write_text("console.log('1');")
    (template / "file1.js").write_text("console.log('old1');")

    (source / "file2.js").write_text("console.log('2');")
    (template / "file2.js").write_text("console.log('old2');")

    (source / "file3.js").write_text("console.log('3');")  # Missing in template
    write_manifest(tmp_path, ["file1.js", "file2.js", "file3.js"])

    result = subprocess.run(
        [sys.executable, "scripts/validate_template_sync.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "file1.js" in result.stdout
    assert "file2.js" in result.stdout
    assert "file3.js" in result.stdout
    assert "(MISSING - needs to be created)" in result.stdout


def test_validator_ignores_non_js_files(tmp_path):
    """Validator should only check .js files."""
    source, template = create_test_structure(tmp_path)

    # Create .js file that matches
    (source / "test.js").write_text("console.log('test');")
    (template / "test.js").write_text("console.log('test');")

    write_manifest(tmp_path, ["test.js"])

    # Create non-.js files that don't match (should be ignored)
    (source / "README.md").write_text("# Source")
    (template / "README.md").write_text("# Template")

    result = subprocess.run(
        [sys.executable, "scripts/validate_template_sync.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    # Should pass because only .js files are checked
    assert result.returncode == 0
    assert "✅ All template files in sync" in result.stdout


def test_validator_checks_exact_template_sync_script_entries(tmp_path):
    """Validator should check non-.github scripts marked for exact template sync."""
    create_test_structure(tmp_path)
    source = tmp_path / "scripts"
    template = tmp_path / "templates" / "consumer-repo" / "scripts"
    source.mkdir(parents=True, exist_ok=True)
    template.mkdir(parents=True, exist_ok=True)

    (source / "aggregate_agent_metrics.py").write_text("SOURCE = True\n", encoding="utf-8")
    (template / "aggregate_agent_metrics.py").write_text("SOURCE = False\n", encoding="utf-8")
    write_raw_manifest(
        tmp_path,
        "\n".join(
            [
                "version: 1",
                "scripts:",
                "  - source: scripts/aggregate_agent_metrics.py",
                "    description: test",
                "    template_sync: exact",
                "",
            ]
        ),
    )

    result = subprocess.run(
        [sys.executable, "scripts/validate_template_sync.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "scripts/aggregate_agent_metrics.py" in result.stdout
    assert "git add templates/consumer-repo/scripts/aggregate_agent_metrics.py" in result.stdout


def test_validator_checks_exact_template_sync_tool_entries(tmp_path):
    """Validator should detect drift in exact-synced consumer tools."""
    create_test_structure(tmp_path)
    source = tmp_path / "tools"
    template = tmp_path / "templates" / "consumer-repo" / "tools"
    source.mkdir(parents=True, exist_ok=True)
    template.mkdir(parents=True, exist_ok=True)

    (source / "llm_registry.py").write_text("MODEL = 'reviewed'\n", encoding="utf-8")
    (template / "llm_registry.py").write_text("MODEL = 'stale'\n", encoding="utf-8")
    write_raw_manifest(
        tmp_path,
        "\n".join(
            [
                "version: 1",
                "scripts:",
                "  - source: tools/llm_registry.py",
                "    description: test",
                "    template_sync: exact",
                "",
            ]
        ),
    )

    result = subprocess.run(
        [sys.executable, "scripts/validate_template_sync.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "tools/llm_registry.py" in result.stdout
    assert "git add templates/consumer-repo/tools/llm_registry.py" in result.stdout


# ---------------------------------------------------------------------------
# In-process tests below.
#
# The tests above exercise the script end-to-end via `subprocess.run`, which
# is faithful to how the validator is actually invoked but runs in a separate
# interpreter that coverage.py never sees -- so despite being thoroughly
# tested, scripts/validate_template_sync.py measured as 0% covered. The tests
# below call the module's functions directly (importing the real module, not
# a copy) so the paths they exercise are both genuinely new coverage AND
# genuinely new assertions: hash_directory() had no test at all, and main()'s
# missing-manifest / invalid-manifest error branches were never exercised by
# any existing test, subprocess or otherwise.
#
# main() resolves its own repo root from `Path(__file__).parent.parent`, so
# these tests point the real module's `__file__` at a fake path under
# tmp_path for the duration of the call -- this runs the *actual* production
# code against a throwaway fixture tree instead of a copy.
# ---------------------------------------------------------------------------


def test_hash_file_matches_manual_sha256(tmp_path: Path) -> None:
    """hash_file() must equal an independently computed SHA256 of the bytes."""
    target = tmp_path / "sample.bin"
    target.write_bytes(b"some content\nwith arbitrary bytes \x00\xff")

    expected = hashlib.sha256(target.read_bytes()).hexdigest()
    assert vts.hash_file(target) == expected


def test_hash_directory_identical_trees_match(tmp_path: Path) -> None:
    """Two directory trees with the same relative paths/content hash equal."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    for root in (a, b):
        (root / "nested").mkdir(parents=True)
        (root / "top.js").write_text("top", encoding="utf-8")
        (root / "nested" / "leaf.js").write_text("leaf", encoding="utf-8")

    assert vts.hash_directory(a) == vts.hash_directory(b)


def test_hash_directory_detects_content_change(tmp_path: Path) -> None:
    """Changing one nested file's content changes the whole directory hash."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    for root in (a, b):
        (root / "nested").mkdir(parents=True)
        (root / "nested" / "leaf.js").write_text("leaf", encoding="utf-8")

    before = vts.hash_directory(b)
    (b / "nested" / "leaf.js").write_text("leaf-changed", encoding="utf-8")
    after = vts.hash_directory(b)

    assert before != after
    assert vts.hash_directory(a) != after


def test_hash_directory_detects_rename_with_identical_content(tmp_path: Path) -> None:
    """A same-content file under a different name must change the hash.

    This is the exact drift the tool exists to catch: if a source file and
    its template counterpart ever swapped names while keeping matching
    bytes, hashing content alone would wrongly call them "in sync".
    """
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "one.js").write_text("same content", encoding="utf-8")
    (b / "renamed.js").write_text("same content", encoding="utf-8")

    assert vts.hash_directory(a) != vts.hash_directory(b)


def test_hash_directory_ignores_empty_subdirectories(tmp_path: Path) -> None:
    """An extra empty subdirectory must not affect the combined hash."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "file.js").write_text("content", encoding="utf-8")
    (b / "file.js").write_text("content", encoding="utf-8")
    (b / "empty_subdir").mkdir()

    assert vts.hash_directory(a) == vts.hash_directory(b)


def test_manifest_template_sync_sources_includes_github_scripts_unmarked(
    tmp_path: Path,
) -> None:
    """.github/scripts/* sources are always template-synced, even unmarked."""
    source, _template = create_test_structure(tmp_path)
    (source / "included.js").write_text("x", encoding="utf-8")
    write_manifest(tmp_path, ["included.js"])  # no template_sync key set

    compiled = compile_manifest(tmp_path / ".github" / "sync-manifest.yml")
    sources = vts._manifest_template_sync_sources(compiled)

    assert sources == [".github/scripts/included.js"]


def test_manifest_template_sync_sources_requires_exact_flag_elsewhere(
    tmp_path: Path,
) -> None:
    """Sources outside .github/scripts/ need an explicit template_sync: exact."""
    plain_dir = tmp_path / "scripts"
    plain_dir.mkdir(parents=True)
    (plain_dir / "plain.py").write_text("x", encoding="utf-8")
    (plain_dir / "exact.py").write_text("x", encoding="utf-8")

    write_raw_manifest(
        tmp_path,
        "\n".join(
            [
                "version: 1",
                "scripts:",
                "  - source: scripts/plain.py",
                "    description: not template-synced",
                "  - source: scripts/exact.py",
                "    description: template-synced",
                "    template_sync: exact",
                "",
            ]
        ),
    )

    compiled = compile_manifest(tmp_path / ".github" / "sync-manifest.yml")
    sources = vts._manifest_template_sync_sources(compiled)

    assert sources == ["scripts/exact.py"]


def test_format_stage_paths_prefixes_template_root() -> None:
    """Each mismatch path must be re-rooted under the template directory, in order."""
    template_root = Path("templates/consumer-repo")
    mismatches = [Path(".github/scripts/a.js"), Path("scripts/b.py")]

    assert vts._format_stage_paths(template_root, mismatches) == [
        "templates/consumer-repo/.github/scripts/a.js",
        "templates/consumer-repo/scripts/b.py",
    ]


def test_main_reports_missing_source_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """main() must fail fast with a clear message when .github/scripts is absent."""
    fake_module_file = tmp_path / "scripts" / "validate_template_sync.py"
    monkeypatch.setattr(vts, "__file__", str(fake_module_file))

    rc = vts.main()

    captured = capsys.readouterr()
    assert rc == 1
    assert "Source directory not found" in captured.out


def test_main_reports_missing_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """main() must fail fast with a clear message when sync-manifest.yml is absent."""
    source = tmp_path / ".github" / "scripts"
    template = tmp_path / "templates" / "consumer-repo" / ".github" / "scripts"
    source.mkdir(parents=True)
    template.mkdir(parents=True)

    fake_module_file = tmp_path / "scripts" / "validate_template_sync.py"
    monkeypatch.setattr(vts, "__file__", str(fake_module_file))

    rc = vts.main()

    captured = capsys.readouterr()
    assert rc == 1
    assert "sync-manifest.yml not found" in captured.out


def test_main_reports_invalid_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """main() must surface a ManifestCompileError instead of crashing."""
    source = tmp_path / ".github" / "scripts"
    template = tmp_path / "templates" / "consumer-repo" / ".github" / "scripts"
    source.mkdir(parents=True)
    template.mkdir(parents=True)
    write_raw_manifest(tmp_path, "version: 2\nscripts: []\n")  # unsupported version

    fake_module_file = tmp_path / "scripts" / "validate_template_sync.py"
    monkeypatch.setattr(vts, "__file__", str(fake_module_file))

    rc = vts.main()

    captured = capsys.readouterr()
    assert rc == 1
    assert "Manifest is invalid" in captured.out
