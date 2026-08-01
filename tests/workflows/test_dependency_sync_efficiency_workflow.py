from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/health-83-dependency-sync-efficiency.yml")


def test_efficiency_workflow_is_manual_weekly_and_advisory():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert data["name"] == "Health 83 Dependency Sync Efficiency"
    assert "workflow_dispatch" in data[True]
    assert data[True]["schedule"]
    assert data["permissions"]["pull-requests"] == "read"
    assert data["permissions"]["issues"] == "write"


def test_efficiency_workflow_collects_fixture_backed_report_and_dedupes_tracker_updates():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/dependency_sync_efficiency_metrics.py" in text
    assert "dependency-sync-efficiency.json" in text
    assert "dependency-sync-efficiency.md" in text
    assert "history_complete" in text
    assert "dependency-sync-efficiency:v1 fingerprint=" in text
    assert "issues.createComment" in text
    assert "actions/upload-artifact@v7" in text
