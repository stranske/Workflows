import os
import subprocess
from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/health-85-ci-time-budget.yml")


def test_daily_budget_is_serialized_advisory_and_keeps_partial_evidence():
    config = yaml.safe_load(WORKFLOW.read_text())
    triggers = config.get("on", config.get(True))
    assert triggers["schedule"] == [{"cron": "35 11 * * *"}]
    assert "workflow_dispatch" in triggers
    assert "pull_request" not in triggers
    assert config["permissions"] == {"contents": "read"}
    assert config["concurrency"]["cancel-in-progress"] is False
    steps = config["jobs"]["report"]["steps"]
    measurement = next(step for step in steps if "tee ci-time-budget.txt" in step.get("run", ""))
    assert (
        measurement["env"]["GH_TOKEN"] == "${{ secrets.OWNER_PR_PAT || secrets.SERVICE_BOT_PAT }}"
    )
    assert steps[0]["with"]["persist-credentials"] is False
    artifact = next(step for step in steps if "actions/upload-artifact@" in step.get("uses", ""))
    assert artifact["if"] == "always()"
    assert "docs/reports/ci-budget.json" in artifact["with"]["path"]
    assert artifact["with"]["retention-days"] == 30


def test_workflow_shell_propagates_reporter_failure_through_tee(tmp_path):
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["report"]["steps"]
    command = next(step["run"] for step in steps if "tee ci-time-budget.txt" in step.get("run", ""))
    stub = tmp_path / "python"
    stub.write_text(
        '#!/bin/sh\ntest "$*" = "-m scripts.ci_time_budget" || exit 9\necho "partial report: API failure"\nexit 1\n'
    )
    stub.chmod(0o755)
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=tmp_path,
        env={**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert (tmp_path / "ci-time-budget.txt").read_text() == "partial report: API failure\n"
