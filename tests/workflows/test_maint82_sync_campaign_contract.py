from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/maint-82-sync-dependabot-campaign.yml")


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
    script = _refresh_script()

    assert "const currentSyncHash = '${{ steps.hash.outputs.hash }}';" in script
    assert "currentSyncHash," in script
