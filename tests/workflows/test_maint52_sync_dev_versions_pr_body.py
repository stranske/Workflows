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


def test_maint52_stages_managed_precommit_repairs():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "if [ -f .pre-commit-config.yaml ]; then git add .pre-commit-config.yaml; fi" in text


def test_maint52_pr_body_reports_canonical_source_commit_and_never_proposes_upstream():
    """AC: Maint 52 reports the settled source commit and never opens an upstream bump."""
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "CANONICAL_SOURCE_SHA" in text
    assert "**Settled source commit:** \\`$CANONICAL_SOURCE_SHA\\`" in text
    assert '--arg source_commit "$CANONICAL_SOURCE_SHA"' in text
    assert "source_commit:$source_commit" in text
    assert "update_versions_from_pypi.py --apply" not in text
    assert "python scripts/update_versions_from_pypi.py --check" in text
