from __future__ import annotations

from pathlib import Path


def test_setup_checklist_stub_points_to_canonical_consumer_checklist() -> None:
    stub = Path("docs/keepalive/SETUP_CHECKLIST.md").read_text(encoding="utf-8")
    checklist = Path("templates/consumer-repo/docs/SETUP_CHECKLIST.md").read_text(encoding="utf-8")

    assert "templates/consumer-repo/docs/SETUP_CHECKLIST.md" in stub
    assert "# Consumer Repository Setup Checklist" in checklist
    assert "Workflow Configuration" in checklist
    assert "scripts/sync_test_dependencies.py" in checklist
    assert "tools/resolve_mypy_pin.py" in checklist
    assert len(checklist) > 40_000


def test_pause_resume_runbook_documents_legacy_pause_alias() -> None:
    runbook = Path("docs/ops/PAUSE_RESUME_RUNBOOK.md").read_text(encoding="utf-8")

    assert "Legacy Alias: `agents:pause`" in runbook
    assert "keepalive_loop.js" in runbook
    assert "keepalive_gate.js" in runbook
    assert "Effect: no-op decoy" not in runbook
