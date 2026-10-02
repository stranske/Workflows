"""Regression coverage for belt ledger completion evidence (issue #3391)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from scripts.audit_belt_ledger_completion import (
    audit_ledger_evidence,
    audit_ledgers,
)
from scripts.audit_belt_ledger_completion import (
    main as audit_main,
)
from scripts.belt_ledger_completion import (
    CompletionEvidenceError,
    commit_files,
    completion_errors,
    duplicate_artifact_errors,
    format_status_counts,
    resolve_completion_commit,
    task_artifacts,
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


def test_commit_files_reports_unverifiable_distinctly(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    ledger = repo / ".agents" / "issue-1-ledger.yml"
    unreachable = "a" * 40
    payload = {
        "version": 1,
        "issue": 1,
        "base": "main",
        "branch": "codex/issue-1",
        "tasks": [_task(unreachable)],
    }
    ledger.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    errors = completion_errors(_task(), unreachable, repo_root=repo)
    findings, unverifiable = audit_ledger_evidence(repo)

    assert len(errors) == 1
    assert "UNVERIFIABLE" in errors[0]
    assert "not evidence of a false completion" in errors[0]
    assert findings == []
    assert len(unverifiable) == 1


def test_commit_files_fails_loud_when_reachable_commit_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    source = repo / "source.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    commit = _commit(repo, "feat: add source")

    def fail_git_show(*args: object, **kwargs: object) -> bytes:
        raise subprocess.CalledProcessError(128, args[0])

    monkeypatch.setattr(subprocess, "check_output", fail_git_show)

    with pytest.raises(CompletionEvidenceError, match="could not be inspected") as exc_info:
        commit_files(commit, repo_root=repo)
    assert type(exc_info.value) is CompletionEvidenceError


def test_task_artifacts_bare_filename_matches_nested_path(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    nested = repo / "sub" / "dir" / "foo.js"
    nested.parent.mkdir(parents=True)
    nested.write_text("export const value = 1;\n", encoding="utf-8")
    commit = _commit(repo, "feat: add nested JavaScript artifact")
    task = _task(commit)
    task["title"] = "Create `foo.js`."

    assert task_artifacts(task) == ["foo.js"]
    assert completion_errors(task, commit, repo_root=repo) == []


def test_task_artifacts_bare_non_ascii_filename_matches_nested_path(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    nested = repo / "src" / "caf\u00e9.js"
    nested.parent.mkdir()
    nested.write_text("export const value = 1;\n", encoding="utf-8")
    commit = _commit(repo, "feat: add non-ASCII JavaScript artifact")
    task = _task(commit)
    task["title"] = "Create `caf\u00e9.js`."

    assert completion_errors(task, commit, repo_root=repo) == []


def test_explicit_root_artifact_does_not_match_nested_basename(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    nested = repo / "examples" / "pyproject.toml"
    nested.parent.mkdir()
    nested.write_text("[build-system]\n", encoding="utf-8")
    commit = _commit(repo, "feat: add example project")
    task = _task(commit)
    task["title"] = "Create `./pyproject.toml`."

    assert task_artifacts(task) == ["./pyproject.toml"]
    assert completion_errors(task, commit, repo_root=repo) == [
        f"task task-01 commit {commit} is missing named artifact(s): ./pyproject.toml"
    ]


def test_audit_cli_reports_all_unverifiable_as_skipped_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    ledger = repo / ".agents" / "issue-1-ledger.yml"
    payload = {
        "version": 1,
        "issue": 1,
        "tasks": [_task("a" * 40)],
    }
    ledger.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    assert audit_main(["--root", str(repo)]) == 0
    output = capsys.readouterr().out
    assert "No invalid belt completion evidence found." in output
    assert "1 completion commit(s) unverifiable (skipped, not findings)." in output


def test_audit_cli_keeps_actionable_findings_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    ledger = repo / ".agents" / "issue-1-ledger.yml"
    ledger.write_text("version: 1\n", encoding="utf-8")
    commit = _commit(repo, "chore: ledger only")
    ledger.write_text(
        yaml.safe_dump(
            {"version": 1, "issue": 1, "tasks": [_task(commit)]},
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert audit_main(["--root", str(repo)]) == 1
    assert "changes only ledger paths" in capsys.readouterr().out


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


def test_duplicate_artifact_scope_ignores_historical_done_task(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    source = repo / "src.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    commit = _commit(repo, "feat: unrelated implementation")
    historical = _task(commit)
    current = _task()
    current["id"] = "task-02"
    current["status"] = "blocked"

    errors = duplicate_artifact_errors(
        [historical, current], repo_root=repo, target_task_id="task-02"
    )

    assert errors == []


def test_root_level_artifact_paths_are_detected() -> None:
    task = {"title": "Update `pyproject.toml` for packaging."}
    assert task_artifacts(task) == ["pyproject.toml"]


def test_resolve_completion_commit_defers_until_agent_lands(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    ledger = repo / ".agents" / "issue-1-ledger.yml"
    ledger.write_text("version: 1\n", encoding="utf-8")
    start = _commit(repo, "chore(ledger): start task task-01 for issue #1")
    task = _task()
    task["status"] = "doing"
    task["commit"] = ""

    assert resolve_completion_commit(task, start, start, repo_root=repo) == (None, [])

    artifact = repo / "docs" / "contracts" / "schemas" / "tracked-variable-v1.schema.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}\n", encoding="utf-8")
    end = _commit(repo, "feat: add tracked variable schema")

    commit, blockers = resolve_completion_commit(task, start, end, repo_root=repo)
    assert blockers == []
    assert commit == end


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
    evidence = workflow.index("resolve_completion_commit")
    done_write = workflow.index("target_task['status'] = 'done'", evidence)
    assert evidence < done_write
    assert "target_task['status'] = 'blocked'" in workflow
    assert (
        "LEDGER_VALIDATE_COMPLETION_TASK_ID: ${{ steps.ledger_finalize.outputs.task_id }}"
    ) in workflow
    assert "steps.ledger_finalize.outcome == 'success'" in workflow
    assert "steps.ledger_final_validation.outcome == 'success'" in workflow
    assert "Belt task counts:" not in workflow  # rendered by the shared helper
