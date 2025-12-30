from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import coverage_history_append


def _write_ndjson(path: Path, records: list[dict[str, object]]) -> None:
    lines = [json.dumps(record, sort_keys=True) for record in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_ndjson(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_load_existing_skips_invalid_lines(tmp_path: Path) -> None:
    history_path = tmp_path / "history.ndjson"
    history_path.write_text('{"run_id": 1}\nnot-json\n\n{"run_id": 2}\n', encoding="utf-8")

    records = coverage_history_append.load_existing(history_path)

    assert records == [{"run_id": 1}, {"run_id": 2}]


def test_main_replaces_matching_run_id_and_sorts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    history_path = tmp_path / "history.ndjson"
    record_path = tmp_path / "record.json"

    _write_ndjson(
        history_path,
        [
            {"run_id": 1, "run_number": 2, "coverage": 70.0},
            {"run_id": 2, "run_number": 1, "coverage": 65.0},
        ],
    )
    record_path.write_text(
        json.dumps({"run_id": 1, "run_number": 3, "coverage": 75.0}),
        encoding="utf-8",
    )

    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("RECORD_PATH", str(record_path))

    exit_code = coverage_history_append.main()

    assert exit_code == 0
    records = _read_ndjson(history_path)
    assert [record["run_id"] for record in records] == [2, 1]
    assert records[1]["coverage"] == 75.0


def test_main_skips_missing_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    history_path = tmp_path / "history.ndjson"
    record_path = tmp_path / "missing.json"

    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("RECORD_PATH", str(record_path))

    exit_code = coverage_history_append.main()

    assert exit_code == 0
    assert not history_path.exists()
