from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/maint-48-docs-drift-audit.yml"


def test_monthly_docs_audit_admits_schedule_and_respects_manual_switch() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    triggers = workflow[True]  # PyYAML represents GitHub Actions' unquoted "on" as True.
    assert triggers["schedule"]
    assert triggers["workflow_dispatch"]["inputs"]["create_issue"]["default"] is True

    steps = workflow["jobs"]["seed-audit"]["steps"]
    create_step = next(step for step in steps if step["name"].startswith("Create the docs-drift"))
    assert " ".join(create_step["if"].split()) == (
        "${{ github.event_name == 'schedule' || "
        "(github.event_name == 'workflow_dispatch' && inputs.create_issue) }}"
    )
