import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LABELS = json.loads((ROOT / ".github/agents/belt-labels.json").read_text())


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_ready_label_constant_is_shared() -> None:
    ready = LABELS["ready"]
    dispatcher = _read(".github/workflows/agents-71-codex-belt-dispatcher.yml")
    worker = _read(".github/workflows/agents-72-codex-belt-worker.yml")
    cleanup = _read("scripts/cleanup_labels.py")

    assert ready == "status:ready"
    assert "const { ready: readyLabel } = require('./.github/agents/belt-labels.json')" in dispatcher
    assert "labels: `agent:${agentKey},${readyLabel}`" in dispatcher
    assert "name: readyLabel" in dispatcher
    assert "ready: readyLabel" in worker
    assert "name: readyLabel" in worker
    assert 'READY_LABEL = BELT_LABELS["ready"]' in cleanup
    assert "READY_LABEL," in cleanup


def test_ready_label_is_applied_somewhere() -> None:
    auto_pilot = _read(".github/workflows/agents-auto-pilot.yml")

    assert "const { ready: readyLabel } = require('./.github/agents/belt-labels.json')" in auto_pilot
    assert "labels: [`agent:${agentKey}`, readyLabel]" in auto_pilot


def test_empty_queue_distinguishes_no_match_from_no_possible_match() -> None:
    dispatcher = _read(".github/workflows/agents-71-codex-belt-dispatcher.yml")

    assert "client.rest.issues.listLabelsForRepo" in dispatcher
    assert "const predicateCanMatch = availableLabels.some" in dispatcher
    assert "The belt queue predicate cannot match: required label" in dispatcher
    assert "No open issues with labels" in dispatcher
