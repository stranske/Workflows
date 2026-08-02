from pathlib import Path

AUTO_UPDATE = Path(".github/workflows/maint-auto-update-pypi-versions.yml")
MAINT50 = Path(".github/workflows/maint-50-tool-version-check.yml")
MAINT52 = Path(".github/workflows/maint-52-sync-dev-versions.yml")


def test_auto_updater_is_the_single_weekly_source_proposal_lane():
    text = AUTO_UPDATE.read_text(encoding="utf-8")

    assert "cron: '0 3 * * 1'" in text
    assert 'scripts/dev_tool_update_policy.py "${args[@]}"' in text
    assert "auto/weekly-dev-tool-update-$(date +%G-W%V)" in text
    assert 'existing_pr=$(gh pr list --head "$branch"' in text
    assert 'git fetch origin "$branch:refs/remotes/origin/$branch"' in text
    assert 'git push --force-with-lease="refs/heads/$branch:$expected_sha"' in text
    assert 'gh pr edit "$existing_pr"' in text


def test_maint50_reports_freshness_without_creating_competing_work():
    text = MAINT50.read_text(encoding="utf-8")

    assert "Create or update issue" not in text
    assert "github.rest.issues.create" not in text
    assert "github.rest.issues.createComment" not in text
    assert "Source proposals belong to maint-auto-update-pypi-versions.yml" in text


def test_maint52_records_the_settled_canonical_source_commit():
    text = MAINT52.read_text(encoding="utf-8")

    assert "canonical_source_sha" in text
    assert "git rev-parse HEAD" in text
    assert "needs.prepare.outputs.canonical_source_sha" in text
