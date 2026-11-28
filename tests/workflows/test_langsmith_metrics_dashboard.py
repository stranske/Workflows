import json
import os
import subprocess
from pathlib import Path

import yaml

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


def test_exact_artifact_lookup_uses_full_inventory_only_when_needed(tmp_path):
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["generate-dashboard"]["steps"]
    command = next(step["run"] for step in steps if step["name"] == "Validate fleet artifacts")
    start = command.index('echo "🔎 Resolving')
    end = command.index("safe_repo=", start)
    selector = command[start:end]
    (tmp_path / ".metrics-tmp/fleet").mkdir(parents=True)

    def lookup(filtered, full, exit_code=0):
        (tmp_path / "filtered").write_text(json.dumps(filtered), encoding="utf-8")
        (tmp_path / "full").write_text(json.dumps(full), encoding="utf-8")
        shell = """
            set -euo pipefail
            repo="example/project"
            artifact_name="metrics.ndjson"
            trusted_workflow_paths='[".github/workflows/gate.yml"]'
            gh() {
              case "$*" in
                *"name=metrics.ndjson"*) echo filtered >&2; cat filtered; return "$FILTER_EXIT" ;;
                *"/actions/runs/7"*) echo ".github/workflows/gate.yml" ;;
                *"/actions/runs/"*) echo "other.yml" ;;
                *) echo full >&2; cat full ;;
              esac
            }
            for entry in once; do
        """
        log = tmp_path / ".metrics-tmp/fleet/fleet_errors.log"
        log.write_text("", encoding="utf-8")
        result = subprocess.run(
            ["bash", "-c", shell + selector + '\nprintf "selected=%s\\n" "$artifact_id"\ndone'],
            env={**os.environ, "FILTER_EXIT": str(exit_code)},
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        )
        selected = [line for line in result.stdout.splitlines() if line.startswith("selected=")]
        return selected, log.read_text(encoding="utf-8").splitlines()

    def artifact(identifier, *, prefix="", timestamp="2026-11-01", expired=False, run=7):
        return {
            "id": identifier,
            "name": prefix + "metrics.ndjson",
            "created_at": timestamp,
            "expired": expired,
            "workflow_run": {"id": run},
        }

    older = artifact(1)
    newest = artifact(2, timestamp="2026-11-05")
    expired = artifact(3, timestamp="2026-11-06", expired=True)
    full = [{"artifacts": [older, newest, expired]}]
    pages = [
        {"artifacts": [newest], "total_count": 3},
        {"artifacts": [older, expired], "total_count": 3},
    ]
    assert lookup(pages, full) == (["selected=2"], ["filtered"])
    assert lookup(pages, full, exit_code=1) == (["selected=2"], ["filtered", "full"])
    for incomplete in (
        [{"artifacts": [older], "total_count": 2}],
        [{"artifacts": [older], "total_count": 2}, {"artifacts": [older], "total_count": 2}],
        [{"artifacts": [older], "total_count": 2}, {"artifacts": [expired], "total_count": 3}],
    ):
        assert lookup(incomplete, full) == (["selected=2"], ["filtered", "full"])
    tied = artifact(4, timestamp="2026-11-05")
    assert lookup(
        [{"artifacts": [tied, newest], "total_count": 2}], [{"artifacts": [newest, tied]}]
    ) == (
        ["selected=4"],
        ["filtered", "full"],
    )
    prefixed = [
        artifact(5, prefix="old-"),
        artifact(6, prefix="new-", timestamp="2026-11-07", run=9),
    ]
    assert lookup([{"artifacts": [expired], "total_count": 1}], [{"artifacts": prefixed}]) == (
        ["selected=5"],
        ["filtered", "full"],
    )
    assert lookup([{"artifacts": []}], [{"artifacts": []}]) == ([], ["filtered", "full"])


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
        "stranske/Orchestrator",
        "stranske/Doc-Lineage",
        "stranske/Deliverable-Render",
        "stranske/Manager-Mosaic",
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
    discovery_line = next(line for line in source.splitlines() if "WORKFLOW_PATH=" in line)

    # Auto-Pilot was retired in #5379; its runs age out of the 7-day window.
    assert "AUTOPILOT_WORKFLOW" not in source
    assert "agents-auto-pilot" not in source
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
    assert '--registry "$REGISTRY" --summary --format markdown --show-unmatched-surfaces' in source
    assert '--registry "$REGISTRY" --summary --format json' in source

    # The same report payload feeds the durable issue and retained report artifact.
    assert "REPORT=$(cat .metrics-tmp/report.md)" in source
    assert "$REPORT" in source
    assert "name: langsmith-metrics-report-${{ github.run_id }}" in source

    # The raw combined NDJSON is retained for downstream durable ingestion.
    assert "name: langsmith-fleet-rollup-${{ github.run_id }}" in source
    assert "path: .metrics-tmp/fleet/combined-fleet.ndjson" in source
    assert "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7" in source
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
