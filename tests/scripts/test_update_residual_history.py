import importlib.util
import json
import pathlib
import sys
import time
import types


def _script_path() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2] / "scripts/update_residual_history.py"


def _run_script() -> None:
    module_name = "scripts.update_residual_history"
    sys.modules.setdefault("scripts", types.ModuleType("scripts"))
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, _script_path())
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)


def test_creates_history_entry_when_files_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(time, "strftime", lambda *_args, **_kwargs: "2025-01-02T03:04:05Z")

    _run_script()

    history_path = tmp_path / "ci/autofix/history.json"
    history = json.loads(history_path.read_text())
    assert len(history) == 1
    entry = history[0]
    assert entry["timestamp"] == "2025-01-02T03:04:05Z"
    assert entry["remaining"] is None
    assert entry["new"] is None
    assert entry["allowed"] is None
    assert entry["by_code"] == {}


def test_uses_report_classification_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    report = {
        "classification": {
            "timestamp": "2024-01-01T00:00:00Z",
            "total": 3,
            "new": 1,
            "allowed": 2,
            "by_code": {"E101": 3},
        }
    }
    pathlib.Path("autofix_report_enriched.json").write_text(json.dumps(report))
    pathlib.Path("ci/autofix").mkdir(parents=True, exist_ok=True)
    pathlib.Path("ci/autofix/history.json").write_text(json.dumps({"not": "a list"}))
    monkeypatch.setattr(time, "strftime", lambda *_args, **_kwargs: "ignored")

    _run_script()

    history = json.loads(pathlib.Path("ci/autofix/history.json").read_text())
    assert history == [
        {
            "allowed": 2,
            "by_code": {"E101": 3},
            "new": 1,
            "remaining": 3,
            "timestamp": "2024-01-01T00:00:00Z",
        }
    ]


def test_trims_history_to_maximum_length(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(time, "strftime", lambda *_args, **_kwargs: "2025-02-02T01:02:03Z")
    history = [{"timestamp": f"item-{idx}"} for idx in range(400)]
    pathlib.Path("ci/autofix").mkdir(parents=True, exist_ok=True)
    pathlib.Path("ci/autofix/history.json").write_text(json.dumps(history))

    _run_script()

    updated = json.loads(pathlib.Path("ci/autofix/history.json").read_text())
    assert len(updated) == 400
    assert updated[0]["timestamp"] == "item-1"
    assert updated[-1]["timestamp"] == "2025-02-02T01:02:03Z"
