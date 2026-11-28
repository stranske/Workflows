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


MAINT_69 = Path(".github/workflows/maint-69-sync-integration-repo.yml")


def _maint_69_steps() -> dict:
    workflow = yaml.safe_load(MAINT_69.read_text(encoding="utf-8"))
    return {step.get("name"): step for step in workflow["jobs"]["sync"]["steps"]}


def test_direct_push_label_sync_is_retired() -> None:
    # Maint 65 pushed straight to default branches and failed on 20 of its last 20 runs
    # (branch protection). Consumers get the guide from the Maint 68 manifest entry above;
    # WIT gets it from the Maint 69 apply step below. One writer per receiver.
    assert not Path(".github/workflows/maint-65-sync-label-docs.yml").exists()
    assert not Path("scripts/sync_label_docs.py").exists()


def test_maint_69_delivers_the_consumer_label_guide_to_wit() -> None:
    workflow = yaml.safe_load(MAINT_69.read_text(encoding="utf-8"))
    source = "templates/consumer-repo/docs/LABELS.md"
    assert source in workflow[True]["push"]["paths"]
    steps = _maint_69_steps()
    assert source in str(steps["Checkout Workflows repo"]["with"]["sparse-checkout"])
    apply_script = str(steps["Apply template updates"]["run"])
    assert f'cp "../workflows/{source}" docs/LABELS.md' in apply_script
    assert "docs/LABELS.md" in str(steps["Commit and push changes"]["run"])


def test_maint_69_apply_step_copies_the_label_guide(tmp_path: Path) -> None:
    """Run the real label-guide lines of the apply heredoc against a scratch checkout."""
    apply_script = str(_maint_69_steps()["Apply template updates"]["run"])
    lines = apply_script.splitlines()
    begin = next(i for i, line in enumerate(lines) if "Sync the consumer label guide" in line)
    end = next(i for i in range(begin, len(lines)) if "Updated docs/LABELS.md" in lines[i])
    snippet = "\n".join(line.strip() for line in lines[begin : end + 1])

    source = tmp_path / "workflows" / "templates" / "consumer-repo" / "docs" / "LABELS.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Labels\n\ncanonical\n", encoding="utf-8")
    receiver = tmp_path / "integration-tests"
    (receiver / "docs").mkdir(parents=True)
    (receiver / "docs" / "LABELS.md").write_text("# Labels\n\nstale\n", encoding="utf-8")

    subprocess.run(["bash", "-euo", "pipefail", "-c", snippet], cwd=receiver, check=True, timeout=5)

    assert (receiver / "docs" / "LABELS.md").read_bytes() == source.read_bytes()


def test_wit_publication_stages_the_label_guide() -> None:
    from scripts import publish_integration_sync

    assert "docs/LABELS.md" in publish_integration_sync.DELIVERY_PATHS


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
