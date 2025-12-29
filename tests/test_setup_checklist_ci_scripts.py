from __future__ import annotations

from pathlib import Path


def test_setup_checklist_mentions_ci_scripts() -> None:
    checklist = Path("docs/keepalive/SETUP_CHECKLIST.md").read_text(encoding="utf-8")

    assert "scripts/sync_test_dependencies.py" in checklist
    assert "tools/resolve_mypy_pin.py" in checklist
