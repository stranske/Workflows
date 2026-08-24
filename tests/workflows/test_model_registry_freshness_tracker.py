"""Maint 77 must preserve the durable lifecycle of its evidence issue."""

from pathlib import Path

WORKFLOW = Path(".github/workflows/maint-77-model-registry-freshness.yml")


def test_model_registry_evidence_issue_is_labeled_durable_on_create_and_refresh() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert '--add-label "automated"' in source
    assert '--add-label "tracker:durable"' in source
    assert '--label "automated,tracker:durable"' in source
