"""Cohesion review B15: one release writer, and no silent token fallback.

release-please (maint-61) writes the GitHub release and pushes the tag with the
Workflows App token; that push is what triggers maint-60, which only moves the
floating v1 tag. A tag pushed with github.token triggers nothing, so a silent
fallback to it froze v1 without any red run.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _steps(name: str) -> list[dict]:
    doc = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    return [step for job in doc["jobs"].values() for step in job.get("steps", [])]


def test_maint60_does_not_write_releases():
    steps = _steps("maint-60-release.yml")
    uses = [str(step.get("uses", "")) for step in steps]
    assert not any("action-gh-release" in u for u in uses), uses
    runs = " ".join(str(step.get("run", "")) for step in steps)
    assert "gh release" not in runs
    move = next(step for step in steps if step.get("name") == "Update floating v1 tag")
    assert move["if"] == "startsWith(github.ref_name, 'v1.')"
    assert 'scripts/update-floating-tag.sh v1 v1. "$GITHUB_SHA"' in move["run"]


def test_maint60_runs_one_tag_at_a_time():
    """Round-2 D11: per-tag concurrency let an older tag's run finish last."""
    doc = yaml.safe_load((WORKFLOWS / "maint-60-release.yml").read_text(encoding="utf-8"))
    assert "github.ref" not in doc["concurrency"]["group"]
    assert doc["concurrency"]["cancel-in-progress"] is False


def test_no_workflow_besides_release_please_creates_releases():
    writers = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        if "action-gh-release" in text or "gh release create" in text:
            writers.append(path.name)
    assert writers == [], writers


def test_maint61_fails_loudly_without_the_app_token():
    steps = _steps("maint-61-release-please.yml")
    mint = next(step for step in steps if step.get("id") == "app_token")
    assert "continue-on-error" not in mint
    assert mint["with"]["client-id"] == "${{ secrets.WORKFLOWS_APP_ID }}"
    assert mint["with"]["private-key"] == "${{ secrets.WORKFLOWS_APP_PRIVATE_KEY }}"
    release = next(step for step in steps if "release-please-action" in str(step.get("uses")))
    assert release["with"]["token"] == "${{ steps.app_token.outputs.token }}"
    text = (WORKFLOWS / "maint-61-release-please.yml").read_text()
    assert "|| github.token" not in text and "${{ github.token }}" not in text


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_floating_tag_moves_to_the_new_release_commit(tmp_path):
    """The maint-60 step itself, against a throwaway origin: v1 ends at the new tag's commit."""
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"),
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    (tmp_path / "gitconfig").write_text("[init]\n\tdefaultBranch = main\n")
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True, env=env)
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", str(work)], check=True, env=env)
    for cmd in (
        ["config", "user.email", "t@example.invalid"],
        ["config", "user.name", "t"],
        ["remote", "add", "origin", str(origin)],
        ["commit", "-q", "--allow-empty", "-m", "one"],
        ["tag", "v1.0.0"],
        ["tag", "v1"],
        ["commit", "-q", "--allow-empty", "-m", "two"],
        ["tag", "v1.0.1"],
        ["push", "-q", "origin", "HEAD:refs/heads/main", "--tags"],
    ):
        subprocess.run(["git", *cmd], cwd=work, check=True, env=env)
    new_sha = _git(work, "rev-parse", "v1.0.1^{commit}")
    script = ROOT / "scripts" / "update-floating-tag.sh"
    subprocess.run(
        ["bash", str(script), "v1", "v1.", new_sha],
        cwd=work,
        check=True,
        env=env,
        capture_output=True,
    )
    remote_v1 = subprocess.run(
        ["git", "ls-remote", str(origin), "refs/tags/v1"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()[0]
    remote_v1_commit = _git(work, "rev-parse", f"{remote_v1}^{{commit}}")
    assert remote_v1_commit == new_sha
