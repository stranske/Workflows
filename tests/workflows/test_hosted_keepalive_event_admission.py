"""Credential-free replay of the hosted keepalive event gate."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(".github/workflows/agents-keepalive-loop.yml")


def _evaluate_job():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["evaluate"]


@pytest.mark.parametrize(
    ("pr_number", "actor", "sweep", "challenge", "should_run", "reason"),
    [
        ("4711", "stranske", "false", "", "true", "ordinary-event"),
        ("004711", "stranske", "false", "", "true", "ordinary-event"),
        ("not-a-number", "stranske", "false", "", None, "Expected a positive PR number"),
        ("0", "stranske", "false", "", None, "Expected a positive PR number"),
        ("4711", "github-actions[bot]", "true", "", "true", "scheduled-sweep-recheck"),
        ("4711", "github-actions[bot]", "true", "present", "true", "due-authority-challenge"),
        ("4372", "renovate[bot]", "false", "", "false", "dependency-bot-pr"),
        ("4372", "dependabot[bot]", "false", "", "false", "dependency-bot-pr"),
        ("", "renovate[bot]", "false", "", "true", "no-pr-context"),
    ],
)
def test_admission_runs_without_external_commands(
    tmp_path, pr_number, actor, sweep, challenge, should_run, reason
):
    gate = next(
        step for step in _evaluate_job()["steps"] if step.get("id") in {"admission", "fingerprint"}
    )
    assert "state-fingerprint-inputs.json" not in gate["run"]
    output = tmp_path / "github-output"
    result = subprocess.run(
        ["/bin/bash", "-e", "-c", gate["run"]],
        cwd=tmp_path,
        env={
            "PATH": str(tmp_path),
            "PR_NUMBER": pr_number,
            "PR_ACTOR": actor,
            "SWEEP_RECHECK": sweep,
            "AUTHORITY_CHALLENGE_FINGERPRINT": challenge,
            "GITHUB_OUTPUT": str(output),
        },
        check=False,
        text=True,
        capture_output=True,
    )
    if should_run is None:
        assert result.returncode == 1
        assert reason in result.stdout
        assert not output.exists()
        return
    assert result.returncode == 0, result.stderr
    assert output.read_text(encoding="utf-8") == f"should_run={should_run}\nreason={reason}\n"


def test_hosted_admission_keeps_retry_security_and_authority_wiring():
    job = _evaluate_job()
    steps = {step.get("id"): step for step in job["steps"] if step.get("id")}
    admission = steps["admission"]
    assert "GH_TOKEN" not in admission["env"]
    assert "GITHUB_TOKEN" not in admission["env"]
    for signal in ("SWEEP_RECHECK", "AUTHORITY_CHALLENGE_FINGERPRINT"):
        env = admission["env"][signal]
        assert "github.event_name == 'workflow_dispatch'" in env
        assert "github.actor == 'github-actions[bot]'" in env
        assert "github.event.inputs.sweep_recheck == 'true'" in env
    for key in ("retry_label", "security_gate", "evaluate", "runner_dispatch"):
        assert "steps.admission.outputs.should_run == 'true'" in steps[key]["if"]
    assert "steps.retry_label.outputs.force_retry" in steps["evaluate"]["env"]["INPUT_FORCE_RETRY"]
    assert "verifyAuthorityChallengeEnvelope" in steps["runner_dispatch"]["run"]
