import importlib
import sys
import types
from pathlib import Path

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
