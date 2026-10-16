"""The consumer template must lint clean under the rules consumers actually select.

Consumer repos select the pep8-naming rules (`N`) in their own pyproject.toml; Workflows' own ruff
selection has no `N`, so a template file that Workflows lints green can turn `lint-ruff` red on
`main` in every consumer after a sync (2026-10-16: scripts/langchain/pr_verifier.py N806 in seven
repos). This test runs the consumer selection, isolated from any local config, on that file.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "consumer-repo" / "scripts" / "langchain" / "pr_verifier.py"
CONSUMER_SELECT = "E,F,I,N,W,UP,B,C4,SIM"


def test_consumer_template_passes_the_consumer_ruff_selection() -> None:
    assert TEMPLATE.is_file(), TEMPLATE
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--isolated",
            "--select",
            CONSUMER_SELECT,
            "--ignore",
            "E501",
            "--line-length",
            "100",
            "--target-version",
            "py312",
            str(TEMPLATE),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_selftest_job_installs_the_consumer_lint_prerequisite():
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/selftest-ci.yml").read_text())
    jobs = workflow["jobs"].values()
    job = next(
        job
        for job in jobs
        if any("tests/workflows/" in step.get("run", "") for step in job["steps"])
    )
    install = next(
        step["run"] for step in job["steps"] if step.get("name") == "Install dependencies"
    )
    assert "ruff==0.17.1" in install
