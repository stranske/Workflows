"""Maint 77 must preserve the durable lifecycle of its evidence issue."""

from pathlib import Path

WORKFLOW = Path(".github/workflows/maint-77-model-registry-freshness.yml")


def test_model_registry_evidence_issue_is_labeled_durable_on_create_and_refresh() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert source.count('--add-label "automated"') == 1
    assert source.count('--add-label "tracker:durable"') == 1
    assert source.count('--label "automated,tracker:durable"') == 1
