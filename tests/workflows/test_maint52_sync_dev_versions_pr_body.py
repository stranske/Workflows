from pathlib import Path

WORKFLOW = Path(".github/workflows/maint-52-sync-dev-versions.yml")


def test_dev_version_sync_pr_body_matches_changed_files():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'changed_files="$(git show --name-only --format= HEAD)"' in text
    assert "grep -qx 'pyproject.toml'" in text
    assert "generated dev-tool pin files" in text
    assert "This PR updates dev tool versions in \\`pyproject.toml\\` to match" not in text
