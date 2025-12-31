import importlib
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest
import yaml


def _load_module(monkeypatch, tmp_path: Path):
    utils_mod = types.ModuleType("utils")
    paths_mod = types.ModuleType("utils.paths")
    paths_mod.proj_path = lambda: tmp_path
    monkeypatch.setitem(sys.modules, "utils", utils_mod)
    monkeypatch.setitem(sys.modules, "utils.paths", paths_mod)
    sys.modules.pop("scripts.ledger_validate", None)
    return importlib.import_module("scripts.ledger_validate")


def test_validate_ledger_reports_schema_errors(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_path = tmp_path / "ledger.yml"
    ledger_path.write_text("- item", encoding="utf-8")

    errors = ledger_validate.validate_ledger(ledger_path)

    assert errors == [f"{ledger_path}: top-level document must be a mapping"]


def test_validate_ledger_flags_invalid_headers(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_path = tmp_path / "ledger.yml"
    payload = {
        "version": 2,
        "issue": "nope",
        "base": "",
        "branch": "",
        "tasks": [],
    }
    ledger_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    errors = ledger_validate.validate_ledger(ledger_path)

    assert f"{ledger_path}: version must be 1" in errors
    assert f"{ledger_path}: issue must be an integer" in errors
    assert f"{ledger_path}: base must be a non-empty string" in errors
    assert f"{ledger_path}: branch must be a non-empty string" in errors
    assert f"{ledger_path}: tasks must be a non-empty list" in errors


def test_validate_ledger_task_rules(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_path = tmp_path / "ledger.yml"
    payload = {
        "version": 1,
        "issue": 123,
        "base": "main",
        "branch": "feature/test",
        "tasks": [
            {
                "id": "task-1",
                "title": "First",
                "status": "doing",
                "finished_at": "2024-01-01T00:00:00Z",
            },
            {
                "id": "task-2",
                "title": "Second",
                "status": "doing",
            },
            {
                "id": "task-3",
                "title": "Third",
                "status": "todo",
                "started_at": "2024-01-01T00:00:00Z",
            },
        ],
    }
    ledger_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    errors = ledger_validate.validate_ledger(ledger_path)

    assert "tasks[0].finished_at must be null unless status is done" in errors
    assert "tasks[2].started_at must be null when status is todo" in errors
    assert f"{ledger_path}: at most one task may have status=doing (found 2)" in errors


def test_commit_validation_for_done_task(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_validate.REPO_ROOT = tmp_path
    ledger_dir = tmp_path / ".agents"
    ledger_dir.mkdir()
    ledger_path = ledger_dir / "issue-1-ledger.yml"
    payload = {
        "version": 1,
        "issue": 1,
        "base": "main",
        "branch": "feature/ledger",
        "tasks": [
            {
                "id": "task-1",
                "title": "Ship it",
                "status": "done",
                "commit": "abcdef1",
            }
        ],
    }
    ledger_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    monkeypatch.setattr(
        ledger_validate, "_commit_files", lambda commit: [".agents/issue-1-ledger.yml"]
    )
    monkeypatch.setattr(ledger_validate, "_commit_subject", lambda commit: "fix: update")

    errors = ledger_validate.validate_ledger(ledger_path)

    assert f"{ledger_path}: tasks[0].commit abcdef1 must include non-ledger changes" in errors


def test_find_ledgers_returns_expected_paths(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_dir = tmp_path / ".agents"
    ledger_dir.mkdir()
    ledger_path = ledger_dir / "issue-5-ledger.yml"
    ledger_path.write_text("version: 1", encoding="utf-8")

    ledgers = ledger_validate.find_ledgers([])

    assert ledgers == [ledger_path]


def test_load_yaml_invalid_raises_ledger_error(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_path = tmp_path / "ledger.yml"
    ledger_path.write_text("foo: [", encoding="utf-8")

    with pytest.raises(ledger_validate.LedgerError) as excinfo:
        ledger_validate._load_yaml(ledger_path)

    assert "invalid YAML" in str(excinfo.value)
    assert excinfo.value.context == str(ledger_path)


def test_validate_timestamp_formats_are_checked(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)

    errors = ledger_validate._validate_timestamp(
        123,
        field="started_at",
        path="tasks[0]",
    )
    assert errors == ["tasks[0].started_at must be a string or null"]

    errors = ledger_validate._validate_timestamp(
        "2024-13-01T00:00:00Z",
        field="finished_at",
        path="tasks[1]",
    )
    assert "tasks[1].finished_at is not a valid timestamp" in errors[0]


def test_validate_timestamp_rejects_non_iso_format(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)

    errors = ledger_validate._validate_timestamp(
        "2024-01-01",
        field="started_at",
        path="tasks[0]",
    )

    assert errors == [
        "tasks[0].started_at must be an ISO-8601 UTC timestamp (YYYY-MM-DDTHH:MM:SSZ)"
    ]


def test_ensure_type_allows_none(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)

    assert ledger_validate._ensure_type(None, str, allow_none=True) is True
    assert ledger_validate._ensure_type(123, str) is False


def test_commit_files_raises_for_unknown_commit(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)

    def raise_called_process_error(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(ledger_validate.subprocess, "check_output", raise_called_process_error)
    monkeypatch.setattr(ledger_validate, "_fetch_commit", lambda commit: False)

    with pytest.raises(ledger_validate.LedgerError, match="unknown commit deadbeef"):
        ledger_validate._commit_files("deadbeef")


def test_fetch_commit_succeeds_without_retry(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    calls: list[list[str]] = []

    def fake_check_call(args, stdout=None, stderr=None):
        calls.append(args)
        return 0

    monkeypatch.setattr(ledger_validate.subprocess, "check_call", fake_check_call)

    assert ledger_validate._fetch_commit("abc1234") is True
    assert calls == [
        [
            "git",
            "fetch",
            "--no-tags",
            "--filter=blob:none",
            "origin",
            "abc1234",
        ]
    ]


def test_fetch_commit_retries_after_deepen(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    calls: list[list[str]] = []

    def fake_check_call(args, stdout=None, stderr=None):
        calls.append(args)
        if args[-1] == "abc1234" and len(calls) == 1:
            raise subprocess.CalledProcessError(1, args)
        return 0

    monkeypatch.setattr(ledger_validate.subprocess, "check_call", fake_check_call)

    assert ledger_validate._fetch_commit("abc1234") is True
    assert calls[0][-1] == "abc1234"
    assert calls[-1][-1] == "abc1234"


def test_fetch_commit_continues_after_failed_retry(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    calls: list[list[str]] = []

    def fake_check_call(args, stdout=None, stderr=None):
        calls.append(args)
        if len(calls) == 1:
            raise subprocess.CalledProcessError(1, args)
        if args[-1] == "abc1234" and len(calls) == 3:
            raise subprocess.CalledProcessError(1, args)
        return 0

    monkeypatch.setattr(ledger_validate.subprocess, "check_call", fake_check_call)

    assert ledger_validate._fetch_commit("abc1234") is True
    assert calls[-1][-1] == "abc1234"


def test_commit_files_fetches_history(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    calls = {"count": 0}

    def fake_check_output(args, text=True):
        calls["count"] += 1
        if calls["count"] == 1:
            raise subprocess.CalledProcessError(1, args)
        return "first.txt\nsecond.txt\n"

    monkeypatch.setattr(ledger_validate.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(ledger_validate, "_fetch_commit", lambda commit: True)

    assert ledger_validate._commit_files("abc1234") == ["first.txt", "second.txt"]


def test_commit_subject_fetches_history(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    calls = {"count": 0}

    def fake_check_output(args, text=True):
        calls["count"] += 1
        if calls["count"] == 1:
            raise subprocess.CalledProcessError(1, args)
        return "fix: subject"

    monkeypatch.setattr(ledger_validate.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(ledger_validate, "_fetch_commit", lambda commit: True)

    assert ledger_validate._commit_subject("abc1234") == "fix: subject"


def test_commit_subject_raises_for_unknown_commit(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)

    def raise_called_process_error(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(ledger_validate.subprocess, "check_output", raise_called_process_error)
    monkeypatch.setattr(ledger_validate, "_fetch_commit", lambda commit: False)

    with pytest.raises(ledger_validate.LedgerError, match="unknown commit deadbeef"):
        ledger_validate._commit_subject("deadbeef")


def test_validate_ledger_rejects_non_mapping_task(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_path = tmp_path / "ledger.yml"
    payload = {
        "version": 1,
        "issue": 1,
        "base": "main",
        "branch": "feature",
        "tasks": ["not-a-mapping"],
    }
    ledger_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    errors = ledger_validate.validate_ledger(ledger_path)

    assert f"{ledger_path}: tasks[0] must be a mapping" in errors


def test_validate_task_commit_rules(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_path = tmp_path / "ledger.yml"

    task = {
        "id": "task-1",
        "title": "Work",
        "status": "done",
        "notes": None,
        "commit": None,
    }
    errors = ledger_validate._validate_task(task, index=0, seen_ids=set(), ledger_path=ledger_path)

    assert "tasks[0].commit is required when status is done" in errors
    assert not any("notes must be a list" in error for error in errors)


def test_validate_task_invalid_fields(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_path = tmp_path / "ledger.yml"

    task = {
        "id": " ",
        "title": "",
        "status": "unknown",
        "notes": ["ok", 1],
        "commit": "bad",
    }

    errors = ledger_validate._validate_task(task, index=0, seen_ids=set(), ledger_path=ledger_path)

    assert "tasks[0].id must be a non-empty string" in errors
    assert "tasks[0].title must be a non-empty string" in errors
    assert "tasks[0].status must be one of" in errors[2]
    assert "tasks[0].notes must be a list of strings" in errors
    assert "tasks[0].commit must be empty or a Git SHA" in errors


def test_validate_task_done_requires_valid_commit(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_path = tmp_path / "ledger.yml"

    task = {
        "id": "task-1",
        "title": "Done",
        "status": "done",
        "commit": "nope",
    }

    errors = ledger_validate._validate_task(task, index=0, seen_ids=set(), ledger_path=ledger_path)

    assert "tasks[0].commit must be a Git SHA (7-40 hex characters)" in errors


def test_validate_task_commit_has_no_files(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_path = tmp_path / "ledger.yml"

    monkeypatch.setattr(ledger_validate, "_commit_files", lambda commit: [])

    task = {
        "id": "task-1",
        "title": "Ship it",
        "status": "done",
        "commit": "abcdef1",
    }

    errors = ledger_validate._validate_task(task, index=0, seen_ids=set(), ledger_path=ledger_path)

    assert f"{ledger_path}: tasks[0].commit abcdef1 has no changed files" in errors


def test_validate_task_commit_type_and_duplicate_ids(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_path = tmp_path / "ledger.yml"
    seen_ids: set[str] = set()

    first = {
        "id": "task-1",
        "title": "First",
        "status": "todo",
        "commit": 123,
    }
    second = {
        "id": "task-1",
        "title": "Second",
        "status": "todo",
    }

    errors = ledger_validate._validate_task(first, index=0, seen_ids=seen_ids, ledger_path=ledger_path)
    errors += ledger_validate._validate_task(second, index=1, seen_ids=seen_ids, ledger_path=ledger_path)

    assert "tasks[0].commit must be a string" in errors
    assert "duplicate task id: task-1" in errors


def test_validate_task_handles_commit_errors(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_validate.REPO_ROOT = tmp_path
    ledger_path = tmp_path / "ledger.yml"

    def raise_commit_files(_commit):
        raise ledger_validate.LedgerError("missing")

    monkeypatch.setattr(ledger_validate, "_commit_files", raise_commit_files)

    task = {
        "id": "task-1",
        "title": "Title",
        "status": "done",
        "commit": "abcdef1",
    }

    errors = ledger_validate._validate_task(task, index=0, seen_ids=set(), ledger_path=ledger_path)

    assert f"{ledger_path}: tasks[0].commit abcdef1 not found in repository" in errors[0]


def test_validate_task_commit_subject_failure(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_validate.REPO_ROOT = tmp_path
    ledger_dir = tmp_path / ".agents"
    ledger_dir.mkdir()
    ledger_path = ledger_dir / "issue-1-ledger.yml"

    monkeypatch.setattr(
        ledger_validate, "_commit_files", lambda commit: [".agents/issue-1-ledger.yml"]
    )

    def raise_subject(_commit):
        raise ledger_validate.LedgerError("no subject")

    monkeypatch.setattr(ledger_validate, "_commit_subject", raise_subject)

    task = {
        "id": "task-1",
        "title": "Ship it",
        "status": "done",
        "commit": "abcdef1",
    }

    errors = ledger_validate._validate_task(task, index=0, seen_ids=set(), ledger_path=ledger_path)

    assert any("not found in repository" in error for error in errors)
    assert any("must include non-ledger changes" in error for error in errors)


def test_validate_task_allows_non_agents_files(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_path = tmp_path / "ledger.yml"

    monkeypatch.setattr(ledger_validate, "_commit_files", lambda commit: ["src/app.py"])
    monkeypatch.setattr(ledger_validate, "_commit_subject", lambda commit: "feat: update")

    task = {
        "id": "task-1",
        "title": "Ship it",
        "status": "done",
        "commit": "abcdef1",
    }

    errors = ledger_validate._validate_task(task, index=0, seen_ids=set(), ledger_path=ledger_path)

    assert errors == []


def test_find_ledgers_respects_explicit_paths(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)

    ledgers = ledger_validate.find_ledgers([str(tmp_path / "one.yml"), str(tmp_path / "two.yml")])

    assert ledgers == [tmp_path / "one.yml", tmp_path / "two.yml"]


def test_find_ledgers_returns_empty_when_missing(tmp_path: Path, monkeypatch) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)

    assert ledger_validate.find_ledgers([]) == []


def test_main_reports_validated_ledgers(tmp_path: Path, monkeypatch, capsys) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_path = tmp_path / "ledger.yml"
    ledger_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "issue": 1,
                "base": "main",
                "branch": "feature",
                "tasks": [
                    {"id": "task-1", "title": "Ok", "status": "todo"},
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(ledger_validate, "find_ledgers", lambda paths: [ledger_path])

    exit_code = ledger_validate.main([])

    assert exit_code == 0
    assert f"Validated {ledger_path}" in capsys.readouterr().out


def test_main_reports_no_ledgers(tmp_path: Path, monkeypatch, capsys) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    monkeypatch.setattr(ledger_validate, "find_ledgers", lambda paths: [])

    exit_code = ledger_validate.main([])

    assert exit_code == 0
    assert "No ledger files found." in capsys.readouterr().out


def test_main_prints_errors_to_stderr(tmp_path: Path, monkeypatch, capsys) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_path = tmp_path / "ledger.yml"
    ledger_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "issue": "nope",
                "base": "main",
                "branch": "feature",
                "tasks": [
                    {"id": "task-1", "title": "Ok", "status": "todo"},
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(ledger_validate, "find_ledgers", lambda paths: [ledger_path])

    exit_code = ledger_validate.main([])

    assert exit_code == 1
    assert "issue must be an integer" in capsys.readouterr().err


def test_main_json_output_includes_errors(tmp_path: Path, monkeypatch, capsys) -> None:
    ledger_validate = _load_module(monkeypatch, tmp_path)
    ledger_path = tmp_path / "ledger.yml"
    ledger_path.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "issue": 10,
                "base": "main",
                "branch": "feature/ledger",
                "tasks": [
                    {
                        "id": "task-1",
                        "title": "Example",
                        "status": "todo",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(ledger_validate, "find_ledgers", lambda paths: [ledger_path])

    exit_code = ledger_validate.main(["--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert str(ledger_path) in payload
    assert any("version must be 1" in msg for msg in payload[str(ledger_path)])
