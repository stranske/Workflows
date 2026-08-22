import json
from pathlib import Path

WORKFLOW = Path(".github/workflows/maint-80-langsmith-metrics-dashboard.yml")
FLEET_REGISTRY = Path("config/langsmith_fleet_registry.json")
FLEET_ALLOWLIST = Path("config/langsmith_fleet_allowlist.json")


def test_fleet_artifact_lookup_does_not_mix_slurp_with_jq() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "--paginate --slurp --method GET" in source
    assert "--arg artifact_name" in source
    assert "select(.name == $artifact_name)" in source
    assert "select(.name != $artifact_name and (.name | endswith($artifact_name)))" in source
    assert "trusted_artifact_workflow_paths" in source
    assert '"/repos/$repo/actions/runs/$candidate_run_id"' in source
    assert "'index($path) != null'" in source
    assert "--slurp --method GET \\\n" in source
    assert '--jq "[.[].artifacts' not in source


def test_fleet_registry_declares_trusted_artifact_workflows() -> None:
    registry = json.loads(FLEET_REGISTRY.read_text(encoding="utf-8"))

    assert registry["trusted_artifact_workflow_paths"] == [
        ".github/workflows/pr-00-gate.yml",
        ".github/workflows/selftest-reusable-ci.yml",
        ".github/workflows/maint-62-integration-consumer.yml",
    ]


def test_every_maintained_consumer_has_an_observability_state() -> None:
    registry = json.loads(FLEET_REGISTRY.read_text(encoding="utf-8"))
    allowlist = json.loads(FLEET_ALLOWLIST.read_text(encoding="utf-8"))

    evidence_modes = {entry["evidence_mode"] for entry in registry["repos"]}
    assert evidence_modes == {"artifact", "langsmith-direct"}
    # Membership is pinned ON PURPOSE: the allowlist is an EXEMPTION from observability, so adding
    # a repo must require a visible test change rather than passing silently.
    assert {entry["repo"] for entry in allowlist["repos"]} == {
        "stranske/Template",
        "stranske/Ready",
        "stranske/Collab-Admin",
        "stranske/Orchestrator",
    }
    assert {entry["status"] for entry in allowlist["repos"]} == {"not-applicable"}


def test_dashboard_skips_direct_evidence_artifact_downloads() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'entry.get("evidence_mode", "artifact") != "artifact"' in source
    assert "continue" in source


def test_dashboard_issue_uses_durable_tracker_labels() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert '--label "metrics,automated,tracker:durable"' in source
    assert '--add-label "tracker:durable"' in source
    assert "metrics,langsmith,automated" not in source
    assert "labels 'metrics,automated,tracker:durable'" in source


def test_run_discovery_targets_workflows_with_runs() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    discovery_line = next(line for line in source.splitlines() if "for WORKFLOW_PATH in" in line)

    assert "agents-auto-pilot.yml" in discovery_line
    assert "agents-verifier.yml" in discovery_line
    assert "reusable-agents-verifier.yml" not in discovery_line


def test_dashboard_issue_upserts_single_pinned_issue() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'ISSUE_TITLE="📊 LangSmith Trace Coverage Dashboard"' in source
    assert "gh issue list \\" in source
    assert 'gh issue edit "$DASHBOARD_ISSUE"' in source
    assert "LangSmith Trace Coverage Report - Week of $START_DATE" not in source


def test_workflows_fleet_entry_is_paused_until_emitter_exists() -> None:
    registry = json.loads(FLEET_REGISTRY.read_text(encoding="utf-8"))
    workflows_entry = next(
        entry for entry in registry["repos"] if entry["repo"] == "stranske/Workflows"
    )

    assert workflows_entry["rollout_status"] == "paused"


def test_fleet_status_is_warning_only_and_appended_to_report() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "::warning title=LangSmith fleet artifacts incomplete::" in source
    assert "cat .metrics-tmp/fleet/fleet-status.md" in source
    assert "if [ -f .metrics-tmp/fleet/fleet-status.md ]; then" in source


def test_fleet_rollup_and_publication_paths_are_wired() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    # Fleet rollup is generated from combined records via the validator summary output.
    assert "python scripts/langsmith_fleet.py .metrics-tmp/fleet/combined-fleet.ndjson" in source
    assert '--registry "$REGISTRY" --summary --format markdown' in source
    assert '--registry "$REGISTRY" --summary --format json' in source

    # The same report payload feeds the durable issue and retained report artifact.
    assert "REPORT=$(cat .metrics-tmp/report.md)" in source
    assert "$REPORT" in source
    assert "name: langsmith-metrics-report-${{ github.run_id }}" in source

    # The raw combined NDJSON is retained for downstream durable ingestion.
    assert "name: langsmith-fleet-rollup-${{ github.run_id }}" in source
    assert "path: .metrics-tmp/fleet/combined-fleet.ndjson" in source
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7" in source
    assert "actions/upload-artifact@v7" not in source
    assert source.count("include-hidden-files: true") >= 3
    assert source.count("            .metrics-tmp/fleet/combined-fleet.ndjson") >= 2


def test_dashboard_publication_cannot_push_to_default_branch() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "contents: read" in source
    assert "contents: write" not in source
    assert "persist-credentials: false" in source
    assert "name: Update dashboard file" not in source
    assert "git push" not in source
    assert '[ "${{ inputs.create_issue }}" == "true" ]' not in source
    assert '[ "$CREATE_ISSUE" == "true" ]' in source
    assert "Authoritative dashboard: durable issue" in source
