from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools.integration_repo import (
    DEFAULT_WORKFLOW_REF,
    WORKFLOW_PLACEHOLDER,
    render_integration_repo,
)


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def test_integration_template_installs_and_tests(tmp_path: Path) -> None:
    destination = tmp_path / "consumer"
    workflow_ref = "owner/repo/.github/workflows/reusable-10-ci-python.yml@ref"

    render_integration_repo(destination, workflow_ref=workflow_ref)

    workflow_file = destination / ".github" / "workflows" / "ci.yml"
    workflow_contents = workflow_file.read_text(encoding="utf-8")

    assert WORKFLOW_PLACEHOLDER not in workflow_contents
    assert workflow_ref in workflow_contents

    _run([sys.executable, "-m", "pip", "install", "-e", ".[test]"], cwd=destination)
    _run([sys.executable, "-m", "pytest"], cwd=destination)


def test_integration_template_default_ref_runs_ci(tmp_path: Path) -> None:
    destination = tmp_path / "default-consumer"

    render_integration_repo(destination)

    workflow_file = destination / ".github" / "workflows" / "ci.yml"
    workflow_contents = workflow_file.read_text(encoding="utf-8")

    assert WORKFLOW_PLACEHOLDER not in workflow_contents
    assert DEFAULT_WORKFLOW_REF in workflow_contents

    _run([sys.executable, "-m", "pip", "install", "-e", ".[test]"], cwd=destination)
    _run([sys.executable, "-m", "pytest"], cwd=destination)
