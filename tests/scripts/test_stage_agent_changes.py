"""Real index/commit regression for normal and pre-timeout agent staging."""

import runpy
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


def make_conflicts(repo, names):
    """Leave real multi-stage index entries from a failed merge."""
    for name in names:
        write(repo, name, "base\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "conflict baseline")
    branch = git(repo, "branch", "--show-current").decode().strip()
    git(repo, "checkout", "-qb", "incoming")
    for name in names:
        write(repo, name, "incoming\n")
    git(repo, "commit", "-qam", "incoming change")
    git(repo, "checkout", "-q", branch)
    for name in names:
        write(repo, name, "ours\n")
    git(repo, "commit", "-qam", "our change")
    result = subprocess.run(["git", "merge", "incoming"], cwd=repo, capture_output=True)
    assert result.returncode == 1, result.stderr
    assert git(repo, "ls-files", "--unmerged", "-z")


def index_bytes(repo):
    return (repo / ".git/index").read_bytes()


def test_resolved_merge_stages_content_and_deletion_preserving_partial_index(repo):
    write(repo, "partial.py", "base\n")
    git(repo, "add", "partial.py")
    git(repo, "commit", "-qm", "partial baseline")
    names = ["source.py", "literal [name] space.py", "deleted.py"]
    make_conflicts(repo, names)
    for name in names[:-1]:
        write(repo, name, "combined resolution\n")
    (repo / "deleted.py").unlink()
    write(repo, "partial.py", "intended staged content\n")
    git(repo, "add", "partial.py")
    write(repo, "partial.py", "later unstaged content\n")
    write(repo, "codex-session-merge.jsonl")
    stage(repo)
    assert git(repo, "ls-files", "--unmerged", "-z") == b""
    assert git(repo, "show", ":partial.py") == b"intended staged content\n"
    git(repo, "commit", "-qm", "resolved merge")
    assert len(git(repo, "rev-list", "--parents", "-n1", "HEAD").split()) == 3
    for name in names[:-1]:
        assert git(repo, "show", f"HEAD:{name}") == b"combined resolution\n"
    assert b"deleted.py" not in git(repo, "ls-tree", "--name-only", "HEAD")
    assert (repo / "partial.py").read_text() == "later unstaged content\n"
    assert b"codex-session-merge.jsonl" not in git(repo, "ls-tree", "--name-only", "HEAD")


@pytest.mark.parametrize("marker_size,crlf", [(7, False), (5, False), (7, True)])
def test_unresolved_markers_refuse_without_changing_index(repo, marker_size, crlf):
    write(repo, ".gitattributes", f"source.py conflict-marker-size={marker_size}\n")
    make_conflicts(repo, ["source.py"])
    if crlf:
        path = repo / "source.py"
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    before = index_bytes(repo)
    result = subprocess.run([sys.executable, str(HELPER)], cwd=repo, capture_output=True)
    assert result.returncode != 0
    assert b"conflict" in result.stdout.lower() + result.stderr.lower()
    assert index_bytes(repo) == before
    assert git(repo, "ls-files", "--unmerged", "-z")


@pytest.mark.parametrize(
    "name",
    [
        "coverage.xml",
        "nested/node_modules/file.py",
        ".workflows-lib/file.py",
        ".github/workflows/agents-test.yml",
        ".github/CODEOWNERS",
        ".github/scripts/agents-guard.js",
        "SECURITY.md",
        "src/access_token.py",
    ],
)
def test_excluded_conflicts_refuse_without_changing_index(repo, name):
    make_conflicts(repo, [name])
    write(repo, name, "resolved\n")
    before = index_bytes(repo)
    result = subprocess.run([sys.executable, str(HELPER)], cwd=repo, capture_output=True)
    assert result.returncode != 0
    assert b"Refusing excluded conflict resolution" in result.stderr
    assert index_bytes(repo) == before
    assert (repo / name).read_text() == "resolved\n"


@pytest.mark.parametrize("parent_link", [False, True])
def test_symlink_resolution_refuses_without_changing_index(repo, tmp_path, parent_link):
    name = "nested/source.py" if parent_link else "source.py"
    make_conflicts(repo, [name])
    target = tmp_path / "external.py"
    target.write_text("resolved\n")
    if parent_link:
        (repo / "nested").rename(repo / "retained")
        (repo / "nested").symlink_to(repo / "retained", target_is_directory=True)
    else:
        (repo / name).unlink()
        (repo / name).symlink_to(target)
    before = index_bytes(repo)
    result = subprocess.run([sys.executable, str(HELPER)], cwd=repo, capture_output=True)
    assert result.returncode != 0
    assert b"Refusing symlink conflict resolution" in result.stderr
    assert index_bytes(repo) == before


def test_directory_resolution_refuses_without_changing_index(repo):
    make_conflicts(repo, ["source.py"])
    (repo / "source.py").unlink()
    write(repo, "source.py/unrelated.py", "not a file resolution\n")
    before = index_bytes(repo)
    result = subprocess.run([sys.executable, str(HELPER)], cwd=repo, capture_output=True)
    assert result.returncode != 0
    assert b"Refusing non-file conflict resolution" in result.stderr
    assert index_bytes(repo) == before


@pytest.mark.parametrize("content", [b"ours\0binary\n", b"non-UTF8 \xff\n"])
def test_non_text_conflict_resolution_refuses(repo, content):
    make_conflicts(repo, ["source.py"])
    (repo / "source.py").write_bytes(content)
    before = index_bytes(repo)
    result = subprocess.run([sys.executable, str(HELPER)], cwd=repo, capture_output=True)
    assert result.returncode != 0
    assert b"Refusing non-text conflict resolution" in result.stderr
    assert index_bytes(repo) == before


def test_git_declared_binary_conflict_is_not_implicitly_resolved_as_ours(repo):
    write(repo, ".gitattributes", "source.py binary\n")
    make_conflicts(repo, ["source.py"])
    assert (repo / "source.py").read_text() == "ours\n"
    before = index_bytes(repo)
    result = subprocess.run([sys.executable, str(HELPER)], cwd=repo, capture_output=True)
    assert result.returncode != 0
    assert b"Refusing non-text conflict resolution" in result.stderr
    assert index_bytes(repo) == before


def test_unmerged_postcondition_refuses_a_silent_staging_noop(repo, monkeypatch):
    make_conflicts(repo, ["source.py"])
    write(repo, "source.py", "resolved\n")
    module = runpy.run_path(str(HELPER), run_name="staging_test")
    module["main"].__globals__["update_index"] = lambda *_: None
    monkeypatch.chdir(repo)
    with pytest.raises(SystemExit, match="Unmerged index entries remain"):
        module["main"]()
    assert git(repo, "ls-files", "--unmerged", "-z")


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
