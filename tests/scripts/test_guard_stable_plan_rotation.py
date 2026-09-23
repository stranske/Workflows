"""A narrow sync plan must not erase still-unmerged stable-delivery content."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.guard_stable_plan_rotation import uncovered_pending_paths


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


def test_shallow_consumer_fetch_recovers_stable_pr_merge_base(tmp_path: Path) -> None:
    repo, old_base, _ = _repo_with_pending_delivery(tmp_path)
    _write(repo, "README.md", "advanced base\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "advance main")
    clone = tmp_path / "shallow-consumer"
    subprocess.run(
        ["git", "clone", "-q", "--depth=1", "--branch", "main", repo.as_uri(), str(clone)],
        check=True,
    )
    assert _git(clone, "rev-parse", "--is-shallow-repository") == "true"
    _git(clone, "fetch", "origin", "sync/workflows-candidate")
    old_head = _git(clone, "rev-parse", "FETCH_HEAD")
    _git(clone, "fetch", "--unshallow", "origin")
    assert _git(clone, "rev-parse", "--is-shallow-repository") == "false"
    assert _git(clone, "merge-base", old_head, "HEAD") == old_base


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
    assert 'git fetch --unshallow origin\n' in workflow
    assert 'git fetch --unshallow origin "$branch_name"' not in workflow
    assert "git diff --cached --name-only > ../staged_sync_targets.txt" in workflow
    assert "--selected-targets-file ../staged_sync_targets.txt" in workflow
    assert (
        workflow.index('git checkout -B "$branch_name"')
        < workflow.index("guard_stable_plan_rotation.py")
        < workflow.index("desired_tree_hash=$(git write-tree)")
    )
