"""Check the Maint 86 shell handoff from the helper to the human-review PR step."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[2] / ".github/workflows/maint-86-model-promotion-prepare.yml"
)


@pytest.mark.parametrize("helper_rc,step_rc", [(0, 0), (10, 0), (2, 2), (1, 1)])
def test_prepare_preserves_helper_status(tmp_path, helper_rc, step_rc):
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["prepare"]["steps"]
    prepare = next(step for step in steps if step.get("id") == "prep")
    open_pr = next(step for step in steps if "create-pull-request@" in step.get("uses", ""))
    helper = tmp_path / "python"
    helper.write_text(f"#!/bin/sh\necho 'benchmark result'\nexit {helper_rc}\n")
    helper.chmod(0o755)
    output = tmp_path / "output"
    summary = tmp_path / "summary"
    env = {
        **os.environ,
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "BENCHMARK_PATH": "benchmark.json",
        "MODE": "auto",
        "GITHUB_OUTPUT": str(output),
        "GITHUB_STEP_SUMMARY": str(summary),
    }

    run = subprocess.run(["bash", "-e", "-c", prepare["run"]], cwd=tmp_path, env=env, check=False)

    assert run.returncode == step_rc
    assert output.read_text().strip() == f"rc={helper_rc}"
    assert "benchmark result" in summary.read_text()
    assert open_pr["if"] == "steps.prep.outputs.rc == '10'"
    assert "needs-human-approval" in open_pr["with"]["labels"]
