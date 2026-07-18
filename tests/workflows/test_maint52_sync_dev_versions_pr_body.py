from pathlib import Path

WORKFLOW = Path(".github/workflows/maint-52-sync-dev-versions.yml")


def test_dev_version_sync_pr_body_matches_changed_files():
    text = WORKFLOW.read_text(encoding="utf-8")
    pr_scope_lines = [
        line.strip() for line in text.splitlines() if line.strip().startswith("pr_scope=")
    ]

    assert 'changed_files="$(git show --name-only --format= HEAD)"' in text
    assert "grep -qx 'pyproject.toml'" in text
    assert pr_scope_lines == [
        'pr_scope="This PR updates dev tool versions in \\`pyproject.toml\\` and related generated dependency files to match the central version pins from [stranske/Workflows](https://github.com/stranske/Workflows)."',
        'pr_scope="This PR updates generated dev-tool pin files to match the central version pins from [stranske/Workflows](https://github.com/stranske/Workflows)."',
    ]
    assert "generated dev-tool pin files" in text
    assert "This PR updates dev tool versions in \\`pyproject.toml\\` to match" not in text


def test_wave_hash_includes_the_sync_implementation():
    text = WORKFLOW.read_text(encoding="utf-8")
    hash_start = text.index("hash=$(\n")
    hash_block = text[hash_start : text.index("\n          )", hash_start)]

    assert "Compute wave hash" in text
    assert ".github/workflows/autofix-versions.env" in hash_block
    assert "scripts/sync_dev_dependencies.py" in hash_block
    assert "| sha256sum" in hash_block
    assert "| cut -d' ' -f1" in hash_block


def test_dev_version_sync_fails_fast_and_checks_uv_lockfiles():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert text.count("set -euo pipefail") >= 2
    assert "if ! uv lock --check; then" in text
    assert "uv_lock_stale=true" in text
