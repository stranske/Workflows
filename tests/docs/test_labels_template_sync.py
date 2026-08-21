"""Keep the consumer label guide bound to its consumer-specific source."""

from pathlib import Path

import yaml


def test_consumer_template_labels_doc_is_the_manifest_source() -> None:
    manifest = yaml.safe_load(Path(".github/sync-manifest.yml").read_text(encoding="utf-8"))
    entries = manifest.get("docs") or []
    labels_entry = [entry for entry in entries if entry.get("target") == "docs/LABELS.md"]

    assert labels_entry == [
        {
            "source": "templates/consumer-repo/docs/LABELS.md",
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
