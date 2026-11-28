import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.workflows.node_tap import assert_named_node_test

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


EXPORT_ACTION_PATH = ".github/actions/export-load-balancer-tokens/action.yml"
MODEL_CONFIG_PATHS = (
    "config/llm_slots.json",
    "config/model_registry.json",
    "config/verifier_semantic_rules.json",
)


@pytest.fixture
def campaign_hash(tmp_path):
    if shutil.which("sha256sum") is None:
        pytest.skip("sha256sum is required to run the authored workflow step")

    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = next(step for step in data["jobs"]["campaign"]["steps"] if step.get("id") == "hash")
    for path in (
        "templates/consumer-repo",
        "tools",
        "scripts",
        ".github/scripts",
        ".github/actions/artifact-cache",
        "config",
    ):
        (tmp_path / path).mkdir(parents=True)
    (tmp_path / ".github/sync-manifest.yml").write_text("version: 1\n", encoding="utf-8")
    export_action = tmp_path / EXPORT_ACTION_PATH
    export_action.parent.mkdir(parents=True)
    export_action.write_text("initial\n", encoding="utf-8")
    for path in MODEL_CONFIG_PATHS:
        (tmp_path / path).write_text("{}\n", encoding="utf-8")
    output = tmp_path / "github-output"

    def read_hash():
        output.write_text("", encoding="utf-8")
        subprocess.run(
            ["bash", "-eo", "pipefail", "-c", step["run"]],
            cwd=tmp_path,
            env={"GITHUB_OUTPUT": str(output), "PATH": os.environ["PATH"]},
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return output.read_text(encoding="utf-8")

    return read_hash


@pytest.mark.parametrize("filename", ["action.yml", "artifact_cache.js"])
def test_campaign_hash_tracks_canonical_artifact_cache(tmp_path, campaign_hash, filename):
    source = tmp_path / ".github/actions/artifact-cache" / filename
    source.write_text("initial\n", encoding="utf-8")
    before = campaign_hash()
    source.write_text("updated\n", encoding="utf-8")
    assert campaign_hash() != before


def test_campaign_hash_tracks_canonical_token_export(tmp_path, campaign_hash):
    before = campaign_hash()
    (tmp_path / EXPORT_ACTION_PATH).write_text("updated\n", encoding="utf-8")
    assert campaign_hash() != before


@pytest.mark.parametrize("path", MODEL_CONFIG_PATHS)
def test_campaign_hash_tracks_canonical_model_config(tmp_path, campaign_hash, path):
    before = campaign_hash()
    (tmp_path / path).write_text('{"changed": true}\n', encoding="utf-8")
    assert campaign_hash() != before


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


def test_maint71_handoffs_preserve_the_dispatch_immutable_binding():
    executor = Path(".github/scripts/maint71_merge_sync_prs.js").read_text(encoding="utf-8")

    assert "plan_id: deliveryRecord?.plan_id || expectedPlanId" in executor
    assert "plan_scope: metadata?.plan_scope || expectedPlanScope" in executor
    assert "scope_base_sha: metadata?.scope_base_sha || expectedScopeBaseSha" in executor
    assert "expectedSourceCommit" in executor


def test_maint71_review_window_handoff_preserves_dispatch_immutable_binding():
    executor = Path(".github/scripts/maint71_merge_sync_prs.js").read_text(encoding="utf-8")
    pending_result = executor.rsplit("if (!reviewWindow.ready) {", 1)[1].split("continue;")[0]

    assert "status: 'review_window_pending'" in pending_result
    assert "plan_id: selection.deliveryRecord?.plan_id || expectedPlanId" in pending_result
    assert "source_commit: selection.deliveryRecord?.source_commit" in pending_result
    assert "delivery_generation: handoffDeliveryGeneration" in pending_result
    assert "canary_baseline_evidence_json" in pending_result
    assert "campaign_no_change_evidence_json" in pending_result
    assert "continuation_lane: requestedSyncHash === 'campaign' ? 'campaign' : ''" in pending_result


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


def test_campaign_forwards_only_evidence_for_the_selected_maint71_lane():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "selector === 'candidate' && continuation.canary_baseline_evidence_json" in workflow
    assert "selector === 'campaign' && continuation.campaign_no_change_evidence_json" in workflow


def test_due_delivery_dispatch_is_scoped_and_manual_admin_cannot_wake_it():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = data["jobs"]["campaign"]["steps"]
    dispatch = next(
        step for step in steps if step.get("name") == "Dispatch due Maint 71 continuations"
    )
    assert dispatch["if"] == "${{ steps.inputs.outputs.dry_run != 'true' }}"
    assert dispatch["env"]["DELIVERY_HANDOFFS_JSON"] == (
        "${{ steps.campaign.outputs.maint71_delivery_handoffs || '[]' }}"
    )

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the authored GitHub scripts")
    test_name = "authored refresh holds blocked peers and dispatches only verified receiver scope"
    result = subprocess.run(
        [
            node,
            "--test",
            "--test-reporter=tap",
            f"--test-name-pattern=^{re.escape(test_name)}$",
            ".github/scripts/__tests__/maint82_continuation_dispatch.test.js",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert_named_node_test(result, test_name)
