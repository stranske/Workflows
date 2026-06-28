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


def test_load_existing_returns_empty_when_missing(tmp_path: Path) -> None:
    history_path = tmp_path / "missing.ndjson"

    records = coverage_history_append.load_existing(history_path)

    assert records == []


def test_main_replaces_matching_run_id_and_sorts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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


def test_main_sorts_by_run_id_when_no_run_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history_path = tmp_path / "history.ndjson"
    record_path = tmp_path / "record.json"

    _write_ndjson(
        history_path,
        [
            {"run_id": 3, "coverage": 50.0},
            {"run_id": 1, "coverage": 45.0},
        ],
    )
    record_path.write_text(
        json.dumps({"run_id": 2, "coverage": 60.0}),
        encoding="utf-8",
    )

    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("RECORD_PATH", str(record_path))

    exit_code = coverage_history_append.main()

    assert exit_code == 0
    records = _read_ndjson(history_path)
    assert [record["run_id"] for record in records] == [1, 2, 3]


def test_main_appends_record_without_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history_path = tmp_path / "history.ndjson"
    record_path = tmp_path / "record.json"

    _write_ndjson(
        history_path,
        [
            {"run_number": 1, "coverage": 50.0},
            {"run_number": 2, "coverage": 55.0},
        ],
    )
    record_path.write_text(
        json.dumps({"run_number": 3, "coverage": 60.0}),
        encoding="utf-8",
    )

    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("RECORD_PATH", str(record_path))

    exit_code = coverage_history_append.main()

    assert exit_code == 0
    records = _read_ndjson(history_path)
    assert len(records) == 3


def test_main_skips_missing_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    history_path = tmp_path / "history.ndjson"
    record_path = tmp_path / "missing.json"

    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("RECORD_PATH", str(record_path))

    exit_code = coverage_history_append.main()

    assert exit_code == 0
    assert not history_path.exists()


def test_main_skips_invalid_record_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    history_path = tmp_path / "history.ndjson"
    record_path = tmp_path / "record.json"
    record_path.write_text("not-json", encoding="utf-8")

    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("RECORD_PATH", str(record_path))

    exit_code = coverage_history_append.main()

    assert exit_code == 0
    assert not history_path.exists()


def test_main_skips_non_dict_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    history_path = tmp_path / "history.ndjson"
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps(["not-a-dict"]), encoding="utf-8")

    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("RECORD_PATH", str(record_path))

    exit_code = coverage_history_append.main()

    assert exit_code == 0
    assert not history_path.exists()


def test_main_handles_record_without_totals_or_covered_line_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that records missing totals or covered-line data are still processed."""
    history_path = tmp_path / "history.ndjson"
    record_path = tmp_path / "record.json"

    # Minimal record without coverage-specific fields
    minimal_record = {"run_id": "test-123", "run_number": 1}
    record_path.write_text(json.dumps(minimal_record), encoding="utf-8")

    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("RECORD_PATH", str(record_path))

    exit_code = coverage_history_append.main()

    assert exit_code == 0
    records = _read_ndjson(history_path)
    assert len(records) == 1
    assert records[0]["run_id"] == "test-123"
    assert records[0]["run_number"] == 1


def test_main_handles_record_without_run_id_or_run_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that records without run_id or run_number are still appended."""
    history_path = tmp_path / "history.ndjson"
    record_path = tmp_path / "record.json"

    # Record with neither run_id nor run_number
    record = {"coverage": 80.0, "other_field": "value"}
    record_path.write_text(json.dumps(record), encoding="utf-8")

    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("RECORD_PATH", str(record_path))

    exit_code = coverage_history_append.main()

    assert exit_code == 0
    records = _read_ndjson(history_path)
    assert len(records) == 1
    assert records[0]["coverage"] == 80.0


def test_main_uses_temporary_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that a temporary file is created and used for atomic write."""
    history_path = tmp_path / "history.ndjson"
    record_path = tmp_path / "record.json"

    _write_ndjson(history_path, [{"run_id": 1, "run_number": 1, "coverage": 50.0}])
    record_path.write_text(
        json.dumps({"run_id": 2, "run_number": 2, "coverage": 60.0}),
        encoding="utf-8",
    )

    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("RECORD_PATH", str(record_path))

    exit_code = coverage_history_append.main()

    assert exit_code == 0
    # Verify the tmp file was created and replaced
    tmp_path_file = history_path.with_suffix(".tmp")
    assert not tmp_path_file.exists()
    records = _read_ndjson(history_path)
    assert len(records) == 2


def test_main_message_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the success message is printed to stdout."""
    history_path = tmp_path / "history.ndjson"
    record_path = tmp_path / "record.json"

    record_path.write_text(
        json.dumps({"run_id": "abc123", "run_number": 1, "coverage": 75.0}),
        encoding="utf-8",
    )

    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("RECORD_PATH", str(record_path))

    exit_code = coverage_history_append.main()

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "[history] appended coverage record run_id=abc123" in captured.out
    assert str(history_path) in captured.out


def test_main_message_on_missing_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the missing record message is printed to stderr."""
    history_path = tmp_path / "history.ndjson"
    record_path = tmp_path / "missing.json"

    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("RECORD_PATH", str(record_path))

    exit_code = coverage_history_append.main()

    assert exit_code == 0
    captured = capsys.readouterr()
    assert f"[history] record file missing: {record_path}" in captured.err


def test_main_message_on_invalid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the parse error message is printed to stderr."""
    history_path = tmp_path / "history.ndjson"
    record_path = tmp_path / "record.json"
    record_path.write_text("not-json", encoding="utf-8")

    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("RECORD_PATH", str(record_path))

    exit_code = coverage_history_append.main()

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "[history] failed to parse record:" in captured.err


def test_main_message_on_non_dict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the non-dict record message is printed to stderr."""
    history_path = tmp_path / "history.ndjson"
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps(["not-a-dict"]), encoding="utf-8")

    monkeypatch.setenv("HISTORY_PATH", str(history_path))
    monkeypatch.setenv("RECORD_PATH", str(record_path))

    exit_code = coverage_history_append.main()

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "[history] record must be a JSON object" in captured.err
