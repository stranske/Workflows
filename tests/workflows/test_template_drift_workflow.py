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
    setup_python_indexes = [
        index
        for index, step in enumerate(steps)
        if re.fullmatch(r"actions/setup-python@v\d+", str(step.get("uses", "")))
    ]
    pyyaml_install_indexes = [
        index
        for index, step in enumerate(steps)
        if "pip install pyyaml" in step.get("run", "").lower()
    ]

    assert len(setup_python_indexes) == 1
    assert len(pyyaml_install_indexes) == 1
    assert setup_python_indexes[0] < pyyaml_install_indexes[0] < checker_index
