"""Execute the hosted Cursor preflight with bounded fake CLI installations."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def steps():
    workflow = yaml.safe_load((ROOT / ".github/workflows/reusable-cursor-run.yml").read_text())
    return {step.get("name"): step for step in workflow["jobs"]["cursor"]["steps"]}


@pytest.mark.parametrize("mode", ["absent", "broken", "working"])
def test_cursor_preflight_executes_version_and_rejects_missing_binary(tmp_path, mode):
    job_steps = steps()
    step = job_steps["Preflight Cursor CLI"]
    cli_dir = tmp_path / "agent-cli/cursor"
    cli_dir.mkdir(parents=True)
    if mode != "absent":
        binary = cli_dir / "cursor-agent"
        binary.write_text(
            "#!/bin/sh\n" + ("exit 42\n" if mode == "broken" else "echo test-version\n")
        )
        binary.chmod(0o755)
    env = {
        **os.environ,
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "GITHUB_PATH": str(tmp_path / "path"),
        "GITHUB_OUTPUT": str(tmp_path / "output"),
    }
    result = subprocess.run(
        ["/bin/bash", "-c", step["run"].replace("${{ runner.temp }}", str(tmp_path))],
        env=env,
        text=True,
        capture_output=True,
    )
    output = (tmp_path / "output").read_text()
    if mode == "working":
        assert result.returncode == 0, result.stderr
        assert "test-version" in result.stdout
        assert "ready=true" in output
    else:
        assert result.returncode != 0
        assert "Cursor CLI preflight failed:" in result.stdout
        assert "error=Cursor CLI preflight failed:" in output
        assert "ready=true" not in output
    exported = (tmp_path / "path").read_text()
    assert str(cli_dir) in exported
    assert str(tmp_path / ".local/bin") in exported


def test_skipped_setup_cannot_enter_cursor_worker(tmp_path):
    run = steps()["Run Cursor"]["run"]
    env = {
        **os.environ,
        "PREFLIGHT_MISSING": "true",
        "PREFLIGHT_ERROR": "Cursor CLI preflight failed: setup did not complete",
        "GITHUB_OUTPUT": str(tmp_path / "output"),
    }
    result = subprocess.run(["/bin/bash", "-c", run], env=env, text=True, capture_output=True)
    assert result.returncode == 1
    output = (tmp_path / "output").read_text()
    assert "exit-code=1" in output
    assert "final-message-summary=Cursor CLI preflight failed:" in output


def test_cursor_setup_runs_after_an_earlier_step_failed():
    for name in [
        "Expose cached Cursor CLI",
        "Cache Cursor CLI",
        "Preflight auth",
        "Ensure Cursor CLI",
        "Preflight Cursor CLI",
    ]:
        assert "!cancelled()" in steps()[name]["if"]
    env = steps()["Run Cursor"]["env"]
    assert "steps.cursor_cli_preflight.outputs.ready != 'true'" in env["PREFLIGHT_MISSING"]
