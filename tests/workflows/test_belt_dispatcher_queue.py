import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LABELS = json.loads((ROOT / ".github/agents/belt-labels.json").read_text())


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_cleanup_uses_the_shared_ready_label() -> None:
    cleanup = _read("scripts/cleanup_labels.py")

    assert LABELS["ready"] == "status:ready"
    assert 'READY_LABEL = BELT_LABELS["ready"]' in cleanup
    assert "READY_LABEL," in cleanup
