"""Run the reusable workflow's delivery shell against real Git repositories."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/reusable-18-autofix.yml"
VENDOR_PATHS = (
    "node_modules/pkg/index.js",
    ".github/scripts/node_modules/pkg/index.js",
    ".workflows-lib/.github/scripts/node_modules/pkg/index.js",
)


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def step(name: str) -> str:
    workflow = yaml.safe_load(WORKFLOW.read_text())
    return next(
        item["run"]
        for job in workflow["jobs"].values()
        for item in job.get("steps", [])
        if item.get("name") == name
    )


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    for name in (*VENDOR_PATHS, "src/example.py"):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("original\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "baseline")
    return repo


def run_step(repo: Path, name: str, *, clean: bool = False) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "MODE_ENABLED": str(clean).lower(),
        "AUTO_CHANGED": "true",
        "CLEAN_CHANGED": "true",
        "AUTO_FILE_LIST": "stale-vendor-list",
        "CLEAN_FILE_LIST": "stale-vendor-list",
        "AUTOFIX_COMMIT_PREFIX": "chore(autofix):",
        "GITHUB_OUTPUT": str(repo.parent / "outputs"),
        "GITHUB_ENV": str(repo.parent / "env"),
    }
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step(name)],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
    )


@pytest.mark.parametrize("vendor", VENDOR_PATHS)
@pytest.mark.parametrize("clean", [False, True])
def test_vendor_only_churn_is_not_deliverable(repository: Path, vendor: str, clean: bool) -> None:
    before = git(repository, "rev-parse", "HEAD")
    (repository / vendor).write_text("installed dependency\n")
    result = run_step(repository, "Consolidate fix mode outputs", clean=clean)
    assert result.returncode == 0, result.stderr
    outputs = (repository.parent / "outputs").read_text()
    assert "changed=false\n" in outputs
    assert "file_list" not in outputs
    assert git(repository, "diff", "--cached", "--name-only") == ""
    assert git(repository, "rev-parse", "HEAD") == before
    assert (repository / vendor).read_text() == "installed dependency\n"


@pytest.mark.parametrize(
    "delivery", ["Commit changes (push path)", "Create patch artifact (fallback)"]
)
def test_source_fix_commits_without_vendor_churn(repository: Path, delivery: str) -> None:
    (repository / VENDOR_PATHS[0]).write_text("installed dependency\n")
    (repository / "src/example.py").write_text("fixed\n")
    result = run_step(repository, "Consolidate fix mode outputs")
    assert result.returncode == 0, result.stderr
    assert "changed=true\n" in (repository.parent / "outputs").read_text()
    result = run_step(repository, delivery)
    assert result.returncode == 0, result.stderr
    assert (
        git(repository, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
        == "src/example.py"
    )
    assert git(repository, "show", f"HEAD:{VENDOR_PATHS[0]}") == "original"
    if delivery == "Create patch artifact (fallback)":
        patch = (repository / "autofix.patch").read_text()
        assert "+fixed" in patch
        assert "node_modules" not in patch


@pytest.mark.parametrize(
    "delivery", ["Commit changes (push path)", "Create patch artifact (fallback)"]
)
def test_real_commit_failure_is_not_hidden(repository: Path, delivery: str) -> None:
    before = git(repository, "rev-parse", "HEAD")
    (repository / "src/example.py").write_text("fixed\n")
    assert run_step(repository, "Consolidate fix mode outputs").returncode == 0
    hook = repository / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    result = run_step(repository, delivery)
    assert result.returncode != 0
    assert git(repository, "rev-parse", "HEAD") == before
    assert not (repository / "autofix.patch").exists()
