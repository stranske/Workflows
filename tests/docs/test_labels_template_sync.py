"""Keep the consumer label guide bound to its consumer-specific source."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml


def test_consumer_template_labels_doc_is_the_manifest_source() -> None:
    manifest = yaml.safe_load(Path(".github/sync-manifest.yml").read_text(encoding="utf-8"))
    entries = manifest.get("docs") or []
    labels_entry = [entry for entry in entries if entry.get("target") == "docs/LABELS.md"]

    assert labels_entry == [
        {
            "source": "docs/LABELS.md",
            "source_tree": "template",
            "target": "docs/LABELS.md",
            "description": "Label definitions and usage",
        }
    ]


def test_consumer_template_labels_exclude_workflows_only_retry_surfaces() -> None:
    root = Path("docs/LABELS.md").read_text(encoding="utf-8")
    template = Path("templates/consumer-repo/docs/LABELS.md").read_text(encoding="utf-8")

    assert "agents-keepalive-loop.yml" in root
    assert "agents-keepalive-loop.yml" not in template
    assert "agents-pr-meta-v4.yml" not in template
    assert "agents-81-gate-followups.yml" in template
    assert "templates/consumer-repo/docs/LABELS.md` → `docs/LABELS.md" in template


def test_dedicated_label_sync_uses_the_consumer_template() -> None:
    workflow = Path(".github/workflows/maint-65-sync-label-docs.yml").read_text(encoding="utf-8")

    assert workflow.count("templates/consumer-repo/docs/LABELS.md") >= 5
    assert "--source docs/LABELS.md" not in workflow


def test_label_sync_inventory_docs_name_the_consumer_source() -> None:
    for path in (
        Path("docs/WORKFLOW_GUIDE.md"),
        Path("docs/ci/WORKFLOWS.md"),
        Path("docs/ci/WORKFLOW_SYSTEM.md"),
        Path("docs/orchestrator/consumer-sync-contract-map.md"),
        Path("docs/workflow-updates/maint-workflow-review-2026-02-22.md"),
        Path("templates/consumer-repo/docs/SETUP_CHECKLIST.md"),
        Path("templates/consumer-repo/WORKFLOW_USER_GUIDE.md"),
    ):
        text = path.read_text(encoding="utf-8")
        assert "templates/consumer-repo/docs/LABELS.md" in text, path


@pytest.mark.parametrize(
    ("token_available", "sync_outcome", "job_status", "dry_run", "expected"),
    [
        ("false", "skipped", "success", "false", "Skipped because no sync token was available."),
        ("true", "success", "success", "true", "Preview completed. No files were pushed."),
        ("true", "success", "success", "false", "Live sync completed. See the sync step log"),
        (
            "true",
            "failure",
            "failure",
            "false",
            "Live sync failed. Some repositories may have been updated.",
        ),
        ("true", "failure", "failure", "true", "Preview failed. No files were pushed."),
        ("false", "skipped", "failure", "false", "Sync did not run. See preceding job steps."),
        ("", "", "failure", "false", "Sync did not run. See preceding job steps."),
    ],
)
def test_dedicated_label_sync_summary_reports_actual_outcome(
    tmp_path, token_available, sync_outcome, job_status, dry_run, expected
) -> None:
    workflow = Path(".github/workflows/maint-65-sync-label-docs.yml")
    steps = {
        step["name"]: step
        for step in yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"]["sync"]["steps"]
    }
    sync = steps["Sync to consumer repos"]
    summary = steps["Summary"]
    assert summary["if"] == "${{ !cancelled() }}"
    assert summary["env"] == {
        "TOKEN_AVAILABLE": "${{ steps.token.outputs.token_available }}",
        "SYNC_OUTCOME": f"${{{{ steps.{sync['id']}.outcome }}}}",
        "JOB_STATUS": "${{ job.status }}",
        "DRY_RUN": sync["env"]["DRY_RUN"],
    }
    assert "continue-on-error" not in sync
    output = tmp_path / "summary"
    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", summary["run"]],
        check=True,
        timeout=5,
        env={
            **os.environ,
            "GITHUB_STEP_SUMMARY": str(output),
            "TOKEN_AVAILABLE": token_available,
            "SYNC_OUTCOME": sync_outcome,
            "JOB_STATUS": job_status,
            "DRY_RUN": dry_run,
        },
    )
    text = output.read_text(encoding="utf-8")
    assert f"**Outcome:** {expected}" in text
    assert "Synced" not in text
