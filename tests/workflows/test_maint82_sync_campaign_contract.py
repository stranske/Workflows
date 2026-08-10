from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/maint-82-sync-dependency-campaign.yml")
MERGE_WORKFLOW = Path(".github/workflows/maint-71-merge-sync-prs.yml")
CAMPAIGN_SCRIPT = Path(".github/scripts/sync_dependency_campaign.js")


def _refresh_script() -> str:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = data["jobs"]["campaign"]["steps"]
    refresh_step = next(step for step in steps if step.get("id") == "campaign")
    return refresh_step["with"]["script"]


def test_campaign_refresh_summary_publishes_source_sync_contract():
    script = _refresh_script()

    assert "result.state.current_sync_hash" in script
    assert "stats.source_sync_status_counts" in script
    assert "Source sync states:" in script
    assert "formatCampaignRunSummaryMarkdown(result.state, result.issue)" in script


def test_campaign_refresh_passes_current_sync_hash_to_runner():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    refresh_step = next(
        step for step in data["jobs"]["campaign"]["steps"] if step.get("id") == "campaign"
    )
    script = refresh_step["with"]["script"]
    env = refresh_step.get("env", {})

    assert env["CURRENT_SYNC_HASH"] == "${{ steps.hash.outputs.hash }}"
    assert "const currentSyncHash = process.env.CURRENT_SYNC_HASH;" in script
    assert "currentSyncHash," in script


def test_campaign_refresh_consumes_maint71_delivery_handoffs():
    script = _refresh_script()

    assert "context.payload.client_payload?.delivery_handoff_records || []" in script
    assert "deliveryHandoffRecords," in script
    assert "Maint 71 handoffs observed:" in script


def test_maint71_dispatches_machine_readable_handoffs_to_campaign():
    # Maint 71 externalized the merge executor into maint71_merge_sync_prs.js
    # (expression-size limit). Contract assertions must follow the executable.
    workflow = MERGE_WORKFLOW.read_text(encoding="utf-8")
    executor = Path(".github/scripts/maint71_merge_sync_prs.js").read_text(encoding="utf-8")
    assert "maint71_merge_sync_prs.js" in workflow
    assert "event_type: 'sync-dependabot-campaign'" in executor
    assert "delivery_handoff_records: report.handoff_records" in executor
    # Targeted Maint 71 runs must still refresh the full registered fleet.
    assert "repos: registeredRepos.join(',')" in executor
    assert "Maint 71 handoff dispatch failed (non-blocking)" in executor


def test_campaign_workflow_bot_agnostic_identity():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    # Renamed bot-agnostic display name (was "Sync/Dependabot Campaign").
    assert data["name"] == "Sync/Dependency Campaign"
    # Loads the renamed campaign script.
    assert "sync_dependency_campaign.js" in _refresh_script()


def test_campaign_tracks_renovate_as_dependency_bot():
    script = CAMPAIGN_SCRIPT.read_text(encoding="utf-8")

    assert "renovate[bot]" in script
    assert "app/renovate" in script
    assert "headRef.startsWith('renovate/')" in script
