"""Health 72's sync commit must start checks on the PR head (round-2 D5).

A push made with GITHUB_TOKEN starts no workflow runs, so the "chore: sync consumer
templates" commit Health 72 pushed left the PR head with no checks. The push now uses
the Workflows App token; without one the step fails with an instruction.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/health-72-template-sync.yml"
SYNC_STEP = "Auto-sync templates for PRs"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps() -> list[dict]:
    return _workflow()["jobs"]["validate"]["steps"]


def test_checkout_credentials_are_the_app_token_and_github_token_only_reads() -> None:
    steps = _steps()
    mint = next(i for i, step in enumerate(steps) if step.get("id") == "app_token")
    checkout = next(
        i
        for i, step in enumerate(steps)
        if str(step.get("uses", "")).startswith("actions/checkout")
    )
    assert mint < checkout
    assert (
        steps[checkout]["with"]["token"] == "${{ steps.app_token.outputs.token || github.token }}"
    )
    assert _workflow()["permissions"] == {"contents": "read"}
    assert "secrets.GITHUB_TOKEN" not in WORKFLOW.read_text(encoding="utf-8")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def _run_sync(tmp_path: Path, minted: str) -> subprocess.CompletedProcess[str]:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", "-b", "feature")
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "t")
    (work / "templates/consumer-repo").mkdir(parents=True)
    (work / "templates/consumer-repo/a.txt").write_text("old\n", encoding="utf-8")
    (work / "scripts").mkdir()
    sync = work / "scripts/sync_templates.sh"
    sync.write_text("#!/bin/sh\necho new > templates/consumer-repo/a.txt\n", encoding="utf-8")
    sync.chmod(0o755)
    _git(work, "add", ".")
    _git(work, "commit", "-q", "-m", "base")
    _git(work, "remote", "add", "origin", str(remote))
    step = next(step for step in _steps() if step.get("name") == SYNC_STEP)
    return subprocess.run(
        ["bash", "-c", step["run"]],
        cwd=work,
        env={**os.environ, "APP_TOKEN_MINTED": minted, "HEAD_REF": "feature"},
        capture_output=True,
        text=True,
    )


def test_needed_sync_without_app_token_fails_with_an_instruction(tmp_path) -> None:
    result = _run_sync(tmp_path, "false")
    assert result.returncode == 1
    assert "::error::templates/consumer-repo is out of sync" in result.stdout
    assert "Run ./scripts/sync_templates.sh" in result.stdout
    branches = subprocess.run(
        ["git", "branch", "--list"], cwd=tmp_path / "remote.git", capture_output=True, text=True
    ).stdout
    assert branches.strip() == "", "nothing may be pushed without the App token"


def test_needed_sync_with_app_token_pushes_the_commit(tmp_path) -> None:
    result = _run_sync(tmp_path, "true")
    assert result.returncode == 0, result.stdout + result.stderr
    log = _git(tmp_path / "remote.git", "log", "--format=%s", "feature")
    assert log.splitlines()[0] == "chore: sync consumer templates"
