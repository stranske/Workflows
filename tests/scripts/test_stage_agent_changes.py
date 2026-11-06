"""Real index/commit regression for normal and pre-timeout agent staging."""

import os
import runpy
import shlex
import shutil
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
    if isinstance(text, bytes):
        p.write_bytes(text)
    else:
        p.write_text(text)


def stage(repo):
    subprocess.run([sys.executable, str(HELPER)], cwd=repo, check=True)


def make_conflicts(repo, names, *, base="base\n", incoming="incoming\n", ours="ours\n"):
    """Leave real multi-stage index entries from a failed merge."""
    for name in names:
        write(repo, name, base)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "conflict baseline")
    branch = git(repo, "branch", "--show-current").decode().strip()
    git(repo, "checkout", "-qb", "incoming")
    for name in names:
        write(repo, name, incoming)
    git(repo, "commit", "-qam", "incoming change")
    git(repo, "checkout", "-q", branch)
    for name in names:
        write(repo, name, ours)
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
    assert b"Unresolved conflict markers" in result.stderr
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


@pytest.mark.parametrize("binary_stage", ["base", "incoming", "ours"])
def test_binary_index_blob_refuses_even_with_text_working_resolution(repo, binary_stage):
    make_conflicts(repo, ["source.py"], **{binary_stage: b"binary\0content\n"})
    # Git leaves text 'ours' untouched when only base/incoming is binary.
    if binary_stage != "ours":
        assert (repo / "source.py").read_text() == "ours\n"
    write(repo, "source.py", "marker-free text\n")
    before = index_bytes(repo)
    result = subprocess.run([sys.executable, str(HELPER)], cwd=repo, capture_output=True)
    assert result.returncode != 0
    assert b"Refusing non-text conflict resolution" in result.stderr
    assert index_bytes(repo) == before


@pytest.mark.parametrize("attribute", ["-merge", "merge=binary"])
def test_binary_merge_attribute_refuses_untouched_text_ours(repo, attribute):
    write(repo, ".gitattributes", f"source.py {attribute}\n")
    make_conflicts(repo, ["source.py"])
    assert (repo / "source.py").read_text() == "ours\n"
    before = index_bytes(repo)
    result = subprocess.run([sys.executable, str(HELPER)], cwd=repo, capture_output=True)
    assert result.returncode != 0
    assert b"Refusing non-text conflict resolution" in result.stderr
    assert index_bytes(repo) == before


def test_binary_default_merge_driver_refuses_untouched_text_ours(repo):
    git(repo, "config", "merge.default", "binary")
    make_conflicts(repo, ["source.py"])
    assert (repo / "source.py").read_text() == "ours\n"
    before = index_bytes(repo)
    result = subprocess.run([sys.executable, str(HELPER)], cwd=repo, capture_output=True)
    assert result.returncode != 0
    assert b"Refusing non-text conflict resolution" in result.stderr
    assert index_bytes(repo) == before


def test_custom_binary_diff_driver_cannot_hide_short_conflict_markers(repo):
    write(repo, ".gitattributes", "source.py diff=foo conflict-marker-size=5\n")
    git(repo, "config", "diff.foo.binary", "true")
    make_conflicts(repo, ["source.py"])
    assert "<<<<< HEAD\n" in (repo / "source.py").read_text()
    # This is the real dependency blind spot; the helper must not rely on it.
    assert git(repo, "diff", "--check") == b""
    before = index_bytes(repo)
    result = subprocess.run([sys.executable, str(HELPER)], cwd=repo, capture_output=True)
    assert result.returncode != 0
    assert b"Refusing non-text conflict resolution" in result.stderr
    assert index_bytes(repo) == before


def test_diff3_base_marker_refuses_without_changing_index(repo):
    git(repo, "config", "merge.conflictStyle", "diff3")
    make_conflicts(repo, ["source.py"])
    path = repo / "source.py"
    lines = path.read_text().splitlines(keepends=True)
    path.write_text(
        "".join(s for s in lines if not s.startswith(("<<<<<<<", "=======", ">>>>>>>")))
    )
    assert "|||||||" in path.read_text()
    before = index_bytes(repo)
    result = subprocess.run([sys.executable, str(HELPER)], cwd=repo, capture_output=True)
    assert result.returncode != 0
    assert b"Unresolved conflict markers" in result.stderr
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


def run_host_commit_stage(repo, tmp_path_factory, agent):
    workflow = yaml.safe_load((ROOT / f".github/workflows/reusable-{agent}-run.yml").read_text())
    script = next(
        s["run"]
        for job in workflow["jobs"].values()
        for s in job.get("steps", [])
        if s.get("name") == "Commit and push changes"
    )
    # Run the real host code through commit, excluding its later push path.
    end = script.index(
        "\n", script.index('git commit -m "', script.index("stage_agent_changes.py"))
    )
    block = script[:end].replace(".workflows-lib/scripts/stage_agent_changes.py", str(HELPER))
    block = block.replace("${{ github.repository }}", "owner/repo")
    tools = tmp_path_factory.mktemp("host-commit-tools")
    real_git = shutil.which("git")
    assert real_git
    wrapper = tools / "git"
    wrapper.write_text(
        '#!/bin/sh\ncase "$1" in fetch|push|pull|rebase) exit 99;; esac\n'
        f'exec {shlex.quote(real_git)} "$@"\n'
    )
    wrapper.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(tools) + os.pathsep + os.environ["PATH"],
        "GITHUB_OUTPUT": str(tools / "output"),
        "GITHUB_REPOSITORY": "owner/repo",
        "MODE": "keepalive",
        "PR_NUMBER": "1",
        "PR_REF": git(repo, "branch", "--show-current").decode().strip(),
        "PUSH_ALLOWED": "true",
        "PUSH_TOKEN": "not-a-real-token",
    }
    return subprocess.run(["bash", "-c", block], cwd=repo, env=env, capture_output=True)


@pytest.mark.parametrize("agent", ["codex", "claude", "cursor", "gemini", "muse"])
@pytest.mark.parametrize("pre_staged", [False, True])
@pytest.mark.parametrize("name", ["source.py", "agents/test.md"])
def test_host_commit_stage_records_an_empty_tree_merge(
    repo, tmp_path_factory, agent, pre_staged, name
):
    make_conflicts(repo, [name])
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    write(repo, name, "ours\n")
    if pre_staged:
        stage(repo)
        assert git(repo, "status", "--porcelain") == b""
    result = run_host_commit_stage(repo, tmp_path_factory, agent)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(git(repo, "rev-list", "--parents", "-n1", "HEAD").split()) == 3
    assert git(repo, "rev-parse", "HEAD^{tree}") == tree
    assert not (repo / ".git/MERGE_HEAD").exists()


def test_muse_bootstrap_only_skip_remains_outside_merges(repo, tmp_path_factory):
    write(repo, "agents/test.md", "baseline\n")
    git(repo, "add", "agents/test.md")
    git(repo, "commit", "-qm", "bootstrap baseline")
    before = git(repo, "rev-parse", "HEAD")
    write(repo, "agents/test.md", "ordinary bootstrap noise\n")
    result = run_host_commit_stage(repo, tmp_path_factory, "muse")
    assert result.returncode == 0, result.stdout + result.stderr
    assert b"skipping commit to reduce noise" in result.stdout
    assert git(repo, "rev-parse", "HEAD") == before


@pytest.mark.parametrize("pre_staged", [False, True])
def test_codex_checkpoint_records_an_empty_tree_merge(repo, pre_staged):
    make_conflicts(repo, ["source.py"])
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    write(repo, "source.py", "ours\n")
    if pre_staged:
        stage(repo)
    text = (ROOT / ".github/workflows/reusable-codex-run.yml").read_text()
    start = text.index('              if [ "$CHANGED" -gt 0 ] || [ "$UNPUSHED" -gt 0 ]')
    end = text.index("                # Rebase onto remote before pushing", start)
    block = textwrap.dedent(text[start:end]) + "\nfi\n"
    block = block.replace(".workflows-lib/scripts/stage_agent_changes.py", str(HELPER))
    env = {**os.environ, "CHANGED": "0" if pre_staged else "1", "UNPUSHED": "0"}
    result = subprocess.run(["bash", "-c", block], cwd=repo, env=env, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(git(repo, "rev-list", "--parents", "-n1", "HEAD").split()) == 3
    assert git(repo, "rev-parse", "HEAD^{tree}") == tree
    assert not (repo / ".git/MERGE_HEAD").exists()


def test_every_runner_calls_shared_contract_and_checkout_includes_scripts():
    for agent in ("codex", "claude", "cursor", "gemini", "muse"):
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
    assert "{ ! git diff --cached --quiet ||" in codex
    assert "git rev-parse -q --verify MERGE_HEAD >/dev/null; }; then" in codex
