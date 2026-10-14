"""Real index/commit regression for normal and pre-timeout agent staging."""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts/stage_agent_changes.py"


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    (tmp_path / "source.py").write_text("initial\n")
    (tmp_path / "coverage.xml").write_text("old coverage\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "baseline")
    return tmp_path


def write(repo, name, text="generated\n"):
    p = repo / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def stage(repo):
    subprocess.run([sys.executable, str(HELPER)], cwd=repo, check=True)


def test_stages_work_preserves_partial_index_and_excludes_runtime_junk(repo):
    write(repo, "source.py", "intended staged version\n")
    git(repo, "add", "source.py")
    write(repo, "source.py", "later unstaged version\n")
    intended = {
        "tests/new test.py",
        "docs/evidence/proof.json",
        "docs/coverage/design.md",
        "source [literal].py",
        "docs/codex-session-example.jsonl",
    }
    junk = {
        "node_modules/a/index.js",
        "nested/node_modules/b/file with spaces.js",
        "codex-session-run.jsonl",
        "claude-session.log",
        "cursor-analysis.json",
        "gemini-output.md",
        "coverage.xml",
        "htmlcov/index.html",
        ".coverage.123",
        ".workflows-lib/scripts/x.py",
        "nested/__pycache__/x.pyc",
    }
    for name in intended | junk:
        write(repo, name)
    # Junk already in the index must also be filtered.
    git(repo, "add", "codex-session-run.jsonl", "nested/node_modules/b/file with spaces.js")
    stage(repo)
    actual = set(
        git(repo, "diff", "--cached", "--name-only", "-z").decode().strip("\0").split("\0")
    )
    assert actual == intended | {"source.py"}
    assert git(repo, "show", ":source.py") == b"intended staged version\n"
    git(repo, "commit", "-qm", "eligible work")
    assert git(repo, "show", "HEAD:source.py") == b"intended staged version\n"
    assert (repo / "source.py").read_text() == "later unstaged version\n"
    for name in junk:
        assert (repo / name).exists()


def test_artifact_only_checkpoint_does_not_commit(repo):
    before = git(repo, "rev-parse", "HEAD")
    write(repo, "coverage.xml")
    write(repo, "codex-session-only.jsonl")
    stage(repo)
    # Execute the actual watchdog staging/commit block, not a copy of its condition.
    text = (ROOT / ".github/workflows/reusable-codex-run.yml").read_text()
    start = text.index("                  if python3 .workflows-lib/scripts/stage_agent_changes.py")
    end = text.index("                  fi", start) + len("                  fi")
    block = textwrap.dedent(text[start:end]).replace(
        ".workflows-lib/scripts/stage_agent_changes.py", str(HELPER)
    )
    subprocess.run(["bash", "-c", block], cwd=repo, check=True)
    assert git(repo, "rev-parse", "HEAD") == before
    assert (repo / "codex-session-only.jsonl").exists()


def test_deletion_and_rename_are_staged(repo):
    (repo / "source.py").rename(repo / "renamed source.py")
    stage(repo)
    git(repo, "commit", "-qm", "rename")
    assert git(repo, "ls-tree", "--name-only", "HEAD") == b"coverage.xml\nrenamed source.py\n"


def test_every_runner_calls_shared_contract_and_checkout_includes_scripts():
    for agent in ("codex", "claude", "cursor", "gemini"):
        p = ROOT / f".github/workflows/reusable-{agent}-run.yml"
        text = p.read_text()
        yaml.safe_load(text)
        assert text.count("python3 .workflows-lib/scripts/stage_agent_changes.py") == (
            2 if agent == "codex" else 1
        )
        assert "git reset HEAD --" not in text
        if agent in ("cursor", "gemini"):
            assert "            scripts\n" in text
    action = (ROOT / ".github/actions/agent-run-base/action.yml").read_text()
    assert "          scripts\n" in action
    codex = (ROOT / ".github/workflows/reusable-codex-run.yml").read_text()
    assert "! git diff --cached --quiet; then\n                    git commit" in codex
