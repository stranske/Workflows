"""Canary marker for authenticated Cursor issue-intake qualification (#3930)."""

from pathlib import Path

MARKER = "issue-intake-cursor-3930-20261016"
CANARY_DOC = Path("docs") / "agents" / "INTAKE_CURSOR_CANARY_3930.md"


def test_intake_cursor_canary_marker() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    canary_path = repo_root / CANARY_DOC
    text = canary_path.read_text(encoding="utf-8")
    assert MARKER in text.splitlines()
