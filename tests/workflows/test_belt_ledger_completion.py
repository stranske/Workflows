"""Regression coverage for belt ledger completion evidence (issue #3391)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from scripts.audit_belt_ledger_completion import audit_ledgers
from scripts.belt_ledger_completion import (
    completion_errors,
    duplicate_artifact_errors,
    format_status_counts,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@example.com")
    (tmp_path / ".agents").mkdir()
    return tmp_path


def _task(commit: str = "") -> dict[str, object]:
    return {
        "id": "task-01",
        "title": "Create `docs/contracts/schemas/tracked-variable-v1.schema.json`.",
        "status": "done" if commit else "doing",
        "started_at": "2026-09-04T20:08:35Z",
        "finished_at": "2026-09-04T20:08:48Z" if commit else None,
        "commit": commit,
        "notes": [],
    }


def test_ledger_only_commit_is_rejected_with_task_and_commit(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    ledger = repo / ".agents" / "issue-3371-ledger.yml"
    ledger.write_text("version: 1\n", encoding="utf-8")
    commit = _commit(repo, "chore(ledger): start task task-01 for issue #3371")

    errors = completion_errors(_task(), commit, repo_root=repo)

    assert f"task task-01 commit {commit} changes only ledger paths" in errors
    assert any("tracked-variable-v1.schema.json" in error for error in errors)


def test_real_artifact_commit_can_complete(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    ledger = repo / ".agents" / "issue-1-ledger.yml"
    ledger.write_text("version: 1\n", encoding="utf-8")
    _commit(repo, "chore: initialise ledger")
    artifact = repo / "docs" / "contracts" / "schemas" / "tracked-variable-v1.schema.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}\n", encoding="utf-8")
    commit = _commit(repo, "feat: add tracked variable schema")

    assert completion_errors(_task(), commit, repo_root=repo) == []


def test_artifact_present_now_but_absent_at_commit_is_blocked(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    source = repo / "src" / "placeholder.py"
    source.parent.mkdir()
    source.write_text("VALUE = 1\n", encoding="utf-8")
    commit = _commit(repo, "feat: unrelated implementation")
    artifact = repo / "docs" / "contracts" / "schemas" / "tracked-variable-v1.schema.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}\n", encoding="utf-8")

    errors = completion_errors(_task(), commit, repo_root=repo)

    assert errors == [
        f"task task-01 commit {commit} is missing named artifact(s): "
        "docs/contracts/schemas/tracked-variable-v1.schema.json"
    ]


def test_duplicate_done_artifact_absence_is_fatal(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    source = repo / "src.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    commit = _commit(repo, "feat: unrelated implementation")
    first = _task(commit)
    second = _task()
    second["id"] = "task-02"
    second["status"] = "todo"

    errors = duplicate_artifact_errors([first, second], repo_root=repo)

    assert len(errors) == 1
    assert "task-01, task-02" in errors[0]
    assert "done task task-01 lacks it" in errors[0]


def test_counts_always_include_all_four_states() -> None:
    assert format_status_counts([{"status": "done"}]) == (
        "Belt task counts: todo=0 in_progress=0 done=1 blocked=0"
    )


def test_read_only_audit_reports_issue_3371_task_01(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    ledger = repo / ".agents" / "issue-3371-ledger.yml"
    ledger.write_text("version: 1\n", encoding="utf-8")
    commit = _commit(repo, "chore(ledger): start task task-01 for issue #3371")
    payload = {
        "version": 1,
        "issue": 3371,
        "base": "main",
        "branch": "codex/issue-3371",
        "tasks": [_task(commit)],
    }
    ledger.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    before = ledger.read_bytes()

    findings = audit_ledgers(repo)

    assert any("issue-3371-ledger.yml task task-01" in finding for finding in findings)
    assert ledger.read_bytes() == before


@pytest.mark.parametrize(
    "workflow_path",
    [
        Path(".github/workflows/agents-72-codex-belt-worker.yml"),
        Path("templates/consumer-repo/.github/workflows/agents-72-codex-belt-worker.yml"),
    ],
)
def test_worker_checks_evidence_before_done_and_gates_persistence(workflow_path: Path) -> None:
    workflow = workflow_path.read_text(encoding="utf-8")
    evidence = workflow.index("blockers = completion_errors")
    done_write = workflow.index("target_task['status'] = 'done'", evidence)
    assert evidence < done_write
    assert "target_task['status'] = 'blocked'" in workflow
    assert "steps.ledger_finalize.outcome == 'success'" in workflow
    assert "steps.ledger_final_validation.outcome == 'success'" in workflow
    assert "Belt task counts:" not in workflow  # rendered by the shared helper
