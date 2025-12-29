from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tools.integration_repo import WORKFLOW_PLACEHOLDER, render_integration_repo


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, env=env)


def test_integration_template_installs_and_tests(tmp_path: Path) -> None:
    destination = tmp_path / "consumer"
    workflow_ref = "owner/repo/.github/workflows/reusable-10-ci-python.yml@ref"

    render_integration_repo(destination, workflow_ref=workflow_ref)

    workflow_file = destination / ".github" / "workflows" / "ci.yml"
    workflow_contents = workflow_file.read_text(encoding="utf-8")

    assert WORKFLOW_PLACEHOLDER not in workflow_contents
    assert workflow_ref in workflow_contents

    user_base = tmp_path / "userbase"
    env = os.environ.copy()
    env["PYTHONUSERBASE"] = str(user_base)

    # Install setuptools first (required for --no-build-isolation with pyproject.toml builds)
    _run(
        [sys.executable, "-m", "pip", "install", "setuptools>=64", "wheel", "--user"],
        cwd=destination,
        env=env,
    )

    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-e",
            ".[test]",
            "--no-build-isolation",
            "--user",
        ],
        cwd=destination,
        env=env,
    )
    _run([sys.executable, "-m", "pytest"], cwd=destination, env=env)
