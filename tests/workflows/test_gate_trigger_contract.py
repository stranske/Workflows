"""Prevent label churn from restarting Gate while commits still supersede runs."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
GATE_FILES = (
    ".github/workflows/pr-00-gate.yml",
    "templates/consumer-repo/.github/workflows/pr-00-gate.yml",
)


@pytest.mark.parametrize("workflow_path", GATE_FILES)
def test_gate_trigger_contract(workflow_path: str) -> None:
    workflow = yaml.safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    # PyYAML's YAML 1.1 resolver reads the Actions key `on` as boolean True.
    triggers = workflow.get("on", workflow.get(True))
    types = triggers["pull_request"]["types"]

    assert "labeled" not in types, f"{workflow_path}: labels must not restart Gate"
    assert "opened" in types, f"{workflow_path}: new PRs must start Gate"
    assert "synchronize" in types, f"{workflow_path}: new commits must start Gate"
    assert workflow["concurrency"]["cancel-in-progress"] is True, (
        f"{workflow_path}: new commits must still supersede in-flight runs"
    )


def test_gate_triggers_match_template() -> None:
    workflows = [yaml.safe_load((ROOT / path).read_text(encoding="utf-8")) for path in GATE_FILES]
    triggers = [workflow.get("on", workflow.get(True)) for workflow in workflows]
    assert triggers[0] == triggers[1], f"Gate triggers must agree across {GATE_FILES}"
