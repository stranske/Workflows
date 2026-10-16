"""Guard the Muse keepalive canary marker."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CANARY_FILE = REPO_ROOT / "docs" / "agents" / "MUSE_CANARY.md"
MARKER = "Muse keepalive canary: 2026-10-16"


def test_muse_canary_file_has_marker() -> None:
    assert CANARY_FILE.exists(), "docs/agents/MUSE_CANARY.md must exist"
    lines = CANARY_FILE.read_text(encoding="utf-8").splitlines()
    assert MARKER in lines, f"{CANARY_FILE} must contain the exact line: {MARKER}"
