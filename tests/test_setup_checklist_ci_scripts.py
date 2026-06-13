from __future__ import annotations

from pathlib import Path


def test_setup_checklist_stub_points_to_canonical_consumer_checklist() -> None:
    stub = Path("docs/keepalive/SETUP_CHECKLIST.md").read_text(encoding="utf-8")
    checklist = Path("templates/consumer-repo/docs/SETUP_CHECKLIST.md").read_text(encoding="utf-8")

    assert "templates/consumer-repo/docs/SETUP_CHECKLIST.md" in stub
    assert "# Consumer Repository Setup Checklist" in checklist
    assert "Workflow Configuration" in checklist
    assert len(checklist) > 40_000
