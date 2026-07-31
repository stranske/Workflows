from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "health-74-template-drift.yml"


def test_template_drift_workflow_installs_pyyaml_before_checker() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["check-drift"]["steps"]

    checker_index = next(
        index
        for index, step in enumerate(steps)
        if "scripts/check_template_drift.py" in step.get("run", "")
    )
    prior_steps = steps[:checker_index]

    setup_python_steps = [
        step
        for step in prior_steps
        if re.fullmatch(r"actions/setup-python@v\d+", str(step.get("uses", "")))
    ]

    assert len(setup_python_steps) == 1
    assert any(
        re.fullmatch(r"actions/setup-python@v\d+", str(step.get("uses", "")))
        for step in prior_steps
    )
    assert any("pip install pyyaml" in step.get("run", "").lower() for step in prior_steps)
