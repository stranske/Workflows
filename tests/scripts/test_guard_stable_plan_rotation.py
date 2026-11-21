"""A narrow sync plan must not erase still-unmerged stable-delivery content."""

from __future__ import annotations

import json
import os
import py_compile
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from scripts.guard_stable_plan_rotation import uncovered_pending_paths
from scripts.scope_consumer_sync_plan import select_plan
from scripts.sync_manifest_compiler import compile_manifest


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _write(repo: Path, path: str, content: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def _repo_with_pending_delivery(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "consumer"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    _write(repo, "README.md", "base\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    old_base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "sync/workflows-candidate")
    _write(repo, "docs/contracts/schemas/mosaic-core-v1.schema.json", "schema\n")
    _write(repo, "scripts/validate_run_contract.py", "validator\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "older full delivery")
    old_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    return repo, old_base, old_head


def test_narrow_rotation_rejects_unmerged_schema_omission(tmp_path: Path) -> None:
    repo, old_base, old_head = _repo_with_pending_delivery(tmp_path)
    uncovered = uncovered_pending_paths(
        repo,
        old_base=old_base,
        old_head=old_head,
        new_base=old_base,
        selected_targets=["scripts/validate_run_contract.py"],
    )
    assert uncovered == ["docs/contracts/schemas/mosaic-core-v1.schema.json"]


def test_narrow_rotation_accepts_selected_directory(tmp_path: Path) -> None:
    repo, old_base, old_head = _repo_with_pending_delivery(tmp_path)
    assert not uncovered_pending_paths(
        repo,
        old_base=old_base,
        old_head=old_head,
        new_base=old_base,
        selected_targets=["scripts/validate_run_contract.py", "docs/contracts/schemas"],
    )


def test_narrow_rotation_rejects_selected_but_skipped_target(tmp_path: Path) -> None:
    repo, old_base, old_head = _repo_with_pending_delivery(tmp_path)
    # A manifest-selected create_only target may be skipped in this consumer.
    # The guard must receive staged paths, not the unfiltered manifest list.
    assert uncovered_pending_paths(
        repo,
        old_base=old_base,
        old_head=old_head,
        new_base=old_base,
        selected_targets=[],
    ) == [
        "docs/contracts/schemas/mosaic-core-v1.schema.json",
        "scripts/validate_run_contract.py",
    ]


def test_narrow_rotation_accepts_prior_schema_already_on_base(tmp_path: Path) -> None:
    repo, old_base, old_head = _repo_with_pending_delivery(tmp_path)
    _write(repo, "docs/contracts/schemas/mosaic-core-v1.schema.json", "schema\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "schema already delivered")
    new_base = _git(repo, "rev-parse", "HEAD")
    assert not uncovered_pending_paths(
        repo,
        old_base=old_base,
        old_head=old_head,
        new_base=new_base,
        selected_targets=["scripts/validate_run_contract.py"],
    )


def test_narrow_rotation_checks_payload_across_multiple_pr_commits(tmp_path: Path) -> None:
    repo, old_base, _ = _repo_with_pending_delivery(tmp_path)
    _git(repo, "checkout", "-q", "sync/workflows-candidate")
    _write(repo, "scripts/validate_run_contract.py", "newer validator\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "later reviewer change")
    old_head = _git(repo, "rev-parse", "HEAD")
    assert uncovered_pending_paths(
        repo,
        old_base=old_base,
        old_head=old_head,
        new_base=old_base,
        selected_targets=["scripts/validate_run_contract.py"],
    ) == ["docs/contracts/schemas/mosaic-core-v1.schema.json"]


def test_narrow_rotation_checks_payload_after_branch_update_merge(tmp_path: Path) -> None:
    repo, _, _ = _repo_with_pending_delivery(tmp_path)
    _write(repo, "README.md", "updated base\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "advance main")
    new_base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "sync/workflows-candidate")
    _git(repo, "merge", "-q", "--no-edit", "main")
    old_head = _git(repo, "rev-parse", "HEAD")
    pr_base = _git(repo, "merge-base", old_head, new_base)
    assert pr_base == new_base
    assert uncovered_pending_paths(
        repo,
        old_base=pr_base,
        old_head=old_head,
        new_base=new_base,
        selected_targets=["scripts/validate_run_contract.py"],
    ) == ["docs/contracts/schemas/mosaic-core-v1.schema.json"]


@pytest.mark.parametrize("merge_main", [False, True])
def test_full_history_consumer_fetch_recovers_stable_pr_merge_base(
    tmp_path: Path, merge_main: bool
) -> None:
    repo, old_base, _ = _repo_with_pending_delivery(tmp_path)
    _git(repo, "config", "uploadpack.allowFilter", "true")
    _write(repo, "README.md", "advanced base\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "advance main")
    new_base = _git(repo, "rev-parse", "HEAD")
    if merge_main:
        _git(repo, "checkout", "-q", "sync/workflows-candidate")
        _git(repo, "merge", "-q", "--no-edit", "main")
        _write(repo, "scripts/validate_run_contract.py", "newer validator\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "later stable change")
        _git(repo, "checkout", "-q", "main")
    clone = tmp_path / "full-history-consumer"
    subprocess.run(
        [
            "git",
            "clone",
            "-q",
            "--filter=blob:none",
            "--single-branch",
            "--branch",
            "main",
            repo.as_uri(),
            str(clone),
        ],
        check=True,
    )
    assert _git(clone, "rev-parse", "--is-shallow-repository") == "false"
    assert _git(clone, "config", "--get", "remote.origin.promisor") == "true"
    _git(clone, "fetch", "origin", "sync/workflows-candidate")
    old_head = _git(clone, "rev-parse", "FETCH_HEAD")
    assert _git(clone, "merge-base", old_head, "HEAD") == (new_base if merge_main else old_base)


def test_narrow_rotation_preserves_pending_executable_mode(tmp_path: Path) -> None:
    repo, old_base, _ = _repo_with_pending_delivery(tmp_path)
    _git(repo, "checkout", "-q", "sync/workflows-candidate")
    (repo / "scripts/validate_run_contract.py").chmod(0o755)
    _git(repo, "add", "scripts/validate_run_contract.py")
    _git(repo, "commit", "-qm", "make validator executable")
    old_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    _write(repo, "scripts/validate_run_contract.py", "validator\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "same bytes, ordinary mode")
    new_base = _git(repo, "rev-parse", "HEAD")
    assert uncovered_pending_paths(
        repo,
        old_base=old_base,
        old_head=old_head,
        new_base=new_base,
        selected_targets=["docs/contracts/schemas"],
    ) == ["scripts/validate_run_contract.py"]


def test_cli_requests_full_scope_for_uncovered_prior_file(tmp_path: Path) -> None:
    repo, old_base, old_head = _repo_with_pending_delivery(tmp_path)
    targets = tmp_path / "sync_targets.txt"
    targets.write_text("scripts/validate_run_contract.py\n")
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [
            "python3",
            str(root / "scripts/guard_stable_plan_rotation.py"),
            "--repo",
            str(repo),
            "--old-base",
            old_base,
            "--old-head",
            old_head,
            "--new-base",
            old_base,
            "--selected-targets-file",
            str(targets),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    assert "source_delta_drops_unmerged_targets" in completed.stderr
    assert "delivery_scope=full" in completed.stderr


def test_maint68_checks_rotation_before_rebuilding_stable_branch() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/maint-68-sync-consumer-repos.yml").read_text()
    assert "guard_stable_plan_rotation.py" in workflow
    assert 'existing_base=$(git merge-base "$existing_head" "$base_sha")' in workflow
    assert 'existing_base=$(git rev-parse "${existing_head}^")' not in workflow
    assert (
        'gh repo clone "$TARGET_REPOSITORY" consumer -- --filter=blob:none --single-branch'
        in workflow
    )
    assert "git fetch --unshallow" not in workflow
    assert "git diff --cached --name-only > ../staged_sync_targets.txt" in workflow
    assert "--selected-targets-file ../staged_sync_targets.txt" in workflow
    assert (
        workflow.index('git checkout -B "$branch_name"')
        < workflow.index("guard_stable_plan_rotation.py")
        < workflow.index("desired_tree_hash=$(git write-tree)")
    )
    assert workflow.index("Staging file target is a directory") < workflow.index(
        'git checkout -B "$branch_name"'
    )


def _maint68_step(name: str) -> str:
    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load(
        (root / ".github/workflows/maint-68-sync-consumer-repos.yml").read_text()
    )
    return next(
        step["run"]
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if step.get("name") == name
    )


def _run_maint68_staging(workspace: Path) -> subprocess.CompletedProcess[str]:
    publish = _maint68_step("Create sync PR")
    # Run the authored opening and staging block without any remote operations.
    opening = publish.partition('branch_name="$SYNC_BRANCH"')[0]
    staging = publish.split("# Stage ONLY manifest-declared targets", 1)[1]
    staging = staging.split('\nif [ "$PLAN_SCOPE"', 1)[0].split("\n", 1)[1]
    return subprocess.run(
        ["bash", "-ec", opening + staging], cwd=workspace, capture_output=True, text=True
    )


@pytest.mark.parametrize("inventory", [None, "", "managed.txt\nobsolete.txt\n"])
def test_maint68_stages_only_with_explicit_inventory(tmp_path: Path, inventory: str | None) -> None:
    repo, _, _ = _repo_with_pending_delivery(tmp_path)
    _write(repo, ".gitignore", "*.pyc\nmanaged.txt\n")
    _write(repo, "obsolete.txt", "managed earlier\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "managed removal fixture")
    _write(repo, "managed.txt", "next payload\n")
    _write(repo, "local.pyc", "ignored fixture\n")
    _write(repo, "README.md", "consumer-owned work\n")
    (repo / "obsolete.txt").unlink()
    if inventory is not None:
        (tmp_path / "sync_targets.txt").write_text(inventory)

    result = _run_maint68_staging(tmp_path)
    if inventory is None:
        assert result.returncode == 1
        assert "sync_targets.txt" in result.stdout
    else:
        assert result.returncode == 0, result.stderr
    expected = "managed.txt\nobsolete.txt" if inventory else ""
    assert _git(repo, "diff", "--cached", "--name-only") == expected


@pytest.mark.parametrize("plan_scope", ["full", "source-delta"])
def test_maint68_directory_hash_copy_and_staging_use_the_same_leaves(
    tmp_path: Path, plan_scope: str
) -> None:
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "workflows"
    source.mkdir()
    _git(source, "init", "-q", "-b", "main")
    directory = "scripts/runner_lib"
    names = ["__init__.py", "__main__.py", "acceptance_gate.py", "core.py"]
    for name in names:
        original = root / directory / name
        _write(source, f"{directory}/{name}", original.read_text())
    _write(source, f"{directory}/.contract[spec].txt", "tracked dotfile\n")
    # The authored publisher supports an older payload without the new hasher.
    for path in ["scripts/sync_status_file_ignores.py", "templates/consumer-repo/.gitignore"]:
        _write(source, path, (root / path).read_text())
    _write(
        source,
        ".github/sync-manifest.yml",
        """version: 1
scripts:
  - source: scripts/runner_lib
    description: Runner library
    is_directory: true
removals:
  - target: obsolete.txt
    description: Explicit removal
  - target: obsolete-directory
    description: Explicit directory removal
""",
    )
    _git(source, "add", ".")
    manifest = source / ".github/sync-manifest.yml"
    plan = compile_manifest(manifest).to_plan()
    source_cache = source / directory / "__pycache__/core.pyc"
    py_compile.compile(str(source / directory / "core.py"), cfile=str(source_cache), doraise=True)
    assert compile_manifest(manifest).to_plan() == plan
    scoped, _ = select_plan(
        plan,
        mode=plan_scope,
        changed_paths=[f"{directory}/core.py"],
        base_sha="a" * 40,
        source_commit="b" * 40,
    )
    _write(tmp_path, "manifest.json", json.dumps(scoped))

    consumer, _, _ = _repo_with_pending_delivery(tmp_path)
    _write(consumer, ".gitignore", "*.pyc\n")
    _write(consumer, "obsolete.txt", "remove this\n")
    _write(consumer, "obsolete-directory/old.txt", "remove this directory\n")
    unrelated = [f"{directory}/.contracts.txt", f"{directory}/consumer-owned.txt"]
    for name in unrelated:
        _write(consumer, name, "consumer baseline\n")
    _git(consumer, "add", ".")
    _git(consumer, "commit", "-qm", "consumer directory fixture")
    for name in unrelated:
        _write(consumer, name, "consumer edit\n")
    cache = f"{directory}/__pycache__/local.pyc"
    _write(consumer, cache, "keep receiving cache\n")

    code = _maint68_step("Detect and apply changes")
    authored = code.split("<< 'SYNC_SCRIPT'\n", 1)[1].split("\nSYNC_SCRIPT", 1)[0]
    env = {
        **os.environ,
        "CURRENT_REPO": "test/fixture",
        "DRY_RUN": "false",
        "FORCE": "true",
        "PLAN_SCOPE": plan_scope,
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
    }

    def apply() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", "-c", authored],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
        )

    collision = f"{directory}/.contract[spec].txt"
    child = f"{collision}/unrelated.txt"
    _write(consumer, child, "unmanaged descendant\n")
    rejected = apply()
    assert rejected.returncode == 1
    assert f"Sync file target is a directory: {collision}" in rejected.stderr
    assert (consumer / child).read_text() == "unmanaged descendant\n"
    assert not (consumer / directory / "core.py").exists()
    assert not (tmp_path / "sync_targets.txt").exists()

    _git(consumer, "--literal-pathspecs", "add", "--", child)
    _git(consumer, "commit", "-qm", "tracked directory collision fixture")
    (consumer / child).unlink()
    (consumer / collision).rmdir()
    rejected = apply()
    assert rejected.returncode == 1
    assert f"Sync file target has a tracked consumer child: {child}" in rejected.stderr
    assert not (consumer / directory / "core.py").exists()
    assert not (tmp_path / "sync_targets.txt").exists()
    _git(consumer, "--literal-pathspecs", "rm", "-q", "--cached", "--", child)
    _git(consumer, "commit", "-qm", "remove tracked collision fixture")

    if plan_scope == "full":
        ignore_path = consumer / ".gitignore"
        ignore_contents = ignore_path.read_bytes()
        ignore_path.unlink()
        ignore_child = ".gitignore/consumer-owned.txt"
        _write(consumer, ignore_child, "consumer directory contents\n")
        rejected = apply()
        assert rejected.returncode == 1
        assert "Sync file target is a directory: .gitignore" in rejected.stderr
        assert (consumer / ignore_child).is_file()
        assert not (consumer / directory / "core.py").exists()
        assert not (tmp_path / "sync_targets.txt").exists()
        _git(consumer, "add", "-A", "--", ".gitignore")
        _git(consumer, "commit", "-qm", "managed ignore path collision fixture")
        (consumer / ignore_child).unlink()
        ignore_path.rmdir()
        rejected = apply()
        assert rejected.returncode == 1
        assert f"Sync file target has a tracked consumer child: {ignore_child}" in rejected.stderr
        assert not (consumer / directory / "core.py").exists()
        assert not (tmp_path / "sync_targets.txt").exists()
        ignore_path.write_bytes(ignore_contents)
        _git(consumer, "add", "-A", "--", ".gitignore")
        _git(consumer, "commit", "-qm", "restore ignore fixture")

    actual = apply()
    assert actual.returncode == 0, actual.stderr
    selected = [f"{directory}/{name}" for name in [*names, ".contract[spec].txt"]]
    full_inventory = [".gitignore", "obsolete.txt", "obsolete-directory"]
    expected_inventory = sorted([*selected, *(full_inventory if plan_scope == "full" else [])])
    assert (tmp_path / "sync_targets.txt").read_text().splitlines() == expected_inventory
    assert not (consumer / directory / "__pycache__/core.pyc").exists()
    assert (consumer / cache).read_text() == "keep receiving cache\n"
    assert source_cache.is_file()
    assert (consumer / "obsolete.txt").exists() == (plan_scope == "source-delta")
    assert (consumer / "obsolete-directory/old.txt").exists() == (plan_scope == "source-delta")
    for name in selected:
        assert (source / name).read_bytes() == (consumer / name).read_bytes()

    # Refuse a new file-to-directory collision before any path is staged.
    copied = (consumer / collision).read_bytes()
    (consumer / collision).unlink()
    _write(consumer, child, "late unmanaged descendant\n")
    rejected = _run_maint68_staging(tmp_path)
    assert rejected.returncode == 1
    assert f"Staging file target is a directory: {collision}" in rejected.stdout
    assert _git(consumer, "diff", "--cached", "--name-only") == ""
    (consumer / child).unlink()
    (consumer / collision).rmdir()
    (consumer / collision).write_bytes(copied)

    staged = _run_maint68_staging(tmp_path)
    assert staged.returncode == 0, staged.stderr
    full_staged = [".gitignore", "obsolete.txt", "obsolete-directory/old.txt"]
    expected_staged = sorted([*selected, *(full_staged if plan_scope == "full" else [])])
    assert _git(consumer, "diff", "--cached", "--name-only").splitlines() == expected_staged
    assert _git(consumer, "diff", "--name-only").splitlines() == unrelated

    # A stale or incomplete checkout refuses before copying or writing the inventory.
    (tmp_path / "sync_targets.txt").unlink()
    (source / directory / "core.py").unlink()
    rejected = apply()
    assert rejected.returncode == 1
    assert "Directory content differs from sync plan: scripts/runner_lib" in rejected.stderr
    assert not (tmp_path / "sync_targets.txt").exists()
