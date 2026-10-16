"""Cursor and Muse each need a presence check that names a missing secret and never echoes it."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECKS = {
    "CURSOR_API_KEY": ROOT / ".github/workflows/health-cursor-auth-check.yml",
    "META_API_KEY": ROOT / ".github/workflows/health-muse-auth-check.yml",
}


def test_each_secret_backed_agent_has_a_presence_check_that_never_echoes_the_key():
    for secret, path in CHECKS.items():
        assert path.exists(), f"{path.name} is missing"
        text = path.read_text()
        doc = yaml.safe_load(text)
        on = doc.get("on") or doc[True]
        assert "schedule" in on and "workflow_dispatch" in on, path.name
        # the only secret the workflow reads is the agent's own key
        assert set(re.findall(r"secrets\.([A-Z0-9_]+)", text)) == {secret}, path.name
        # the value is never printed or written anywhere: no echo/printf/cat/tee of $SECRET
        leaks = re.findall(rf"(?:echo|printf|cat|tee)[^\n]*\$\{{?{secret}\b", text)
        assert not leaks, f"{path.name} prints the secret: {leaks}"
        assert "${{ secrets." + secret + " }}" in text, path.name
        assert "exit 1" in text, f"{path.name} must fail loudly when the key is missing"


def test_muse_check_is_never_billable():
    text = CHECKS["META_API_KEY"].read_text()
    assert "muse exec" in text
    assert "--provider echo" in text
    assert "META_API_KEY= MUSE_NO_AUTO_UPDATE=1 timeout 60 muse exec" in text
    assert "--sandbox-network restricted" in text
    assert "muse --version" in text
    assert "command -v bwrap" not in text
    assert "sudo sysctl" not in text


def test_muse_startup_failure_is_not_masked_by_a_working_system_sandbox(tmp_path):
    import os
    import subprocess

    doc = yaml.safe_load(CHECKS["META_API_KEY"].read_text())
    step = next(step for step in doc["jobs"]["check"]["steps"] if step.get("id") == "cli")
    # Run the actual probe body, stubbing only the installed executable. No download,
    # key, real Muse session, or system configuration command runs in this test.
    probe = step["run"][step["run"].index("# Exercise Muse's own startup") :]
    binary = tmp_path / "muse"
    binary.write_text('#!/bin/sh\n[ "$1" != exec ] || exit 42\nexit 0\n')
    binary.chmod(0o755)
    system = tmp_path / "bwrap"
    system.write_text("#!/bin/sh\nexit 0\n")
    system.chmod(0o755)
    timeout = tmp_path / "timeout"
    timeout.write_text('#!/bin/sh\nshift\nexec "$@"\n')
    timeout.chmod(0o755)
    output = tmp_path / "output"
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "GITHUB_OUTPUT": str(output),
    }
    result = subprocess.run(
        ["bash", "-c", probe], env=env, capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
    assert "sandbox=failed" in output.read_text()
    binary.write_text('#!/bin/sh\n[ "$1" != exec ] || [ "$3" = echo ] || exit 43\nexit 0\n')
    output.write_text("")
    result = subprocess.run(
        ["bash", "-c", probe], env=env, capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
    assert "sandbox=ok" in output.read_text()
