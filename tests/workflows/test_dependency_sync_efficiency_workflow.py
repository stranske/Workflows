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
    assert "window_complete" in text
    assert "trailing-7-day-window" in text
    assert "createTokenAwareRetry" in text
    assert "workflows-consumer-sync:v1" in text
    assert "sync-pr-delivery-record:v1" in text
    assert "Number.isNaN(Date.parse(value))" in text
    assert "listEventsForTimeline" in text
    assert "head_ref_force_pushed" in text
    assert "ready_for_review" in text
    assert "collectRunWindow" in text
    assert "...params" in text
    assert "workflow runs: ${error.message}" in text
    assert "window_complete: collectionFailures.length === 0" in text
    assert "dependency-sync-efficiency:v1 fingerprint=" in text
    assert 'metrics_output="$(python scripts/dependency_sync_efficiency_metrics.py' in text
    assert "awk -F= '/^fingerprint=/{print $2}'" in text
    assert "from scripts.dependency_sync_efficiency_metrics import fingerprint" not in text
    assert "issues.createComment" in text
    assert "EFFICIENCY_TRACKER_ISSUE: '2897'" in text
    assert "tracker === 1836" in text
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in text


def test_dedicated_health83_contract_retains_unknown_collection_boundary():
    from pathlib import Path

    contract = (
        Path(__file__).resolve().parents[2] / "docs/ops/DEPENDENCY_SYNC_EFFICIENCY.md"
    ).read_text()
    assert "dense or inconsistent workflow-run intervals" in contract
    assert "advisory `unknown`" in contract
    assert "cannot guarantee an atomic snapshot" in contract
