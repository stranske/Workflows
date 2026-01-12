"""Tests for scripts/validate_template_sync.py"""

import shutil
import subprocess
import sys
from pathlib import Path


def create_test_structure(tmp_path: Path) -> tuple[Path, Path]:
    """Create temporary source and template directories."""
    source = tmp_path / ".github" / "scripts"
    template = tmp_path / "templates" / "consumer-repo" / ".github" / "scripts"
    source.mkdir(parents=True)
    template.mkdir(parents=True)

    # Copy validator script to tmp_path so it can find paths relative to cwd
    script_dir = tmp_path / "scripts"
    script_dir.mkdir(parents=True)
    shutil.copy("scripts/validate_template_sync.py", script_dir / "validate_template_sync.py")

    return source, template


def test_validator_passes_when_files_match(tmp_path):
    """Validator should exit 0 when source and template files match."""
    source, template = create_test_structure(tmp_path)

    # Create matching files
    (source / "test.js").write_text("console.log('test');")
    (template / "test.js").write_text("console.log('test');")

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
    """Validator should suggest running sync script when validation fails."""
    source, template = create_test_structure(tmp_path)

    (source / "test.js").write_text("console.log('source');")
    (template / "test.js").write_text("console.log('template');")

    result = subprocess.run(
        [sys.executable, "scripts/validate_template_sync.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "./scripts/sync_templates.sh" in result.stdout


def test_validator_handles_multiple_mismatches(tmp_path):
    """Validator should report all mismatched files."""
    source, template = create_test_structure(tmp_path)

    # Create multiple mismatches
    (source / "file1.js").write_text("console.log('1');")
    (template / "file1.js").write_text("console.log('old1');")

    (source / "file2.js").write_text("console.log('2');")
    (template / "file2.js").write_text("console.log('old2');")

    (source / "file3.js").write_text("console.log('3');")  # Missing in template

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
