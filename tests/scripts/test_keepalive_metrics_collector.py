from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts import keepalive_metrics_collector as collector


def _sample_record() -> dict:
    return {
        "pr_number": 101,
        "iteration": 2,
        "timestamp": datetime(2025, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        "action": "retry",
        "error_category": "none",
        "duration_ms": 4321,
        "tasks_total": 5,
        "tasks_complete": 3,
    }


def test_validate_record_accepts_valid_payload() -> None:
    record = _sample_record()

    collector.validate_record(record)


def test_validate_record_rejects_missing_fields() -> None:
    record = {"pr_number": 101}

    with pytest.raises(collector.ValidationError):
        collector.validate_record(record)


def test_validate_record_rejects_invalid_types() -> None:
    record = _sample_record()
    record["duration_ms"] = "fast"

    with pytest.raises(collector.ValidationError):
        collector.validate_record(record)


def test_validate_record_rejects_invalid_timestamp() -> None:
    record = _sample_record()
    record["timestamp"] = "not-a-timestamp"

    with pytest.raises(collector.ValidationError):
        collector.validate_record(record)


def test_append_record_appends_lines(tmp_path: Path) -> None:
    record = _sample_record()
    path = tmp_path / "metrics.ndjson"

    collector.append_record(path, record)
    collector.append_record(path, record)

    lines = path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert lines[0] == lines[1]


def test_is_int_rejects_bool() -> None:
    assert collector._is_int(3) is True
    assert collector._is_int(True) is False


def test_parse_timestamp_validates_timezone() -> None:
    parsed = collector._parse_timestamp("2025-02-03T04:05:06Z")

    assert parsed.tzinfo is not None

    with pytest.raises(collector.ValidationError, match="timestamp must include timezone"):
        collector._parse_timestamp("2025-02-03T04:05:06")

    with pytest.raises(collector.ValidationError, match="timestamp is required"):
        collector._parse_timestamp("")


def test_coerce_int_rejects_invalid_value() -> None:
    with pytest.raises(collector.ValidationError, match="duration_ms must be an integer"):
        collector._coerce_int("fast", "duration_ms")


def test_build_record_from_args_defaults_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collector, "_utc_now_iso", lambda: "2025-04-05T06:07:08Z")
    args = collector.argparse.Namespace(
        pr_number="12",
        iteration="3",
        timestamp=None,
        action="retry",
        error_category="none",
        duration_ms="123",
        tasks_total="7",
        tasks_complete="5",
    )

    record = collector.build_record_from_args(args)

    assert record["timestamp"] == "2025-04-05T06:07:08Z"
    assert record["pr_number"] == 12
    assert record["tasks_complete"] == 5


def test_load_record_from_json_adds_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collector, "_utc_now_iso", lambda: "2025-06-07T08:09:10Z")

    record = collector.load_record_from_json('{"pr_number": 9}')

    assert record["timestamp"] == "2025-06-07T08:09:10Z"


def test_load_record_from_json_rejects_invalid_payloads() -> None:
    with pytest.raises(collector.ValidationError, match="record_json must be valid JSON"):
        collector.load_record_from_json("{")

    with pytest.raises(collector.ValidationError, match="record_json must decode to an object"):
        collector.load_record_from_json('["list"]')


def test_iter_errors_formats_validation_error() -> None:
    error = collector.ValidationError("bad record")

    assert list(collector._iter_errors(error)) == ["bad record"]

    assert list(collector._iter_errors(ValueError("nope"))) == ["nope"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("pr_number", True, "pr_number must be an integer"),
        ("iteration", "two", "iteration must be an integer"),
        ("action", "  ", "action must be a non-empty string"),
        ("error_category", "", "error_category must be a non-empty string"),
        ("tasks_total", "ten", "tasks_total must be an integer"),
        ("tasks_complete", None, "tasks_complete must be an integer"),
    ],
)
def test_validate_record_rejects_specific_fields(field: str, value: object, message: str) -> None:
    record = _sample_record()
    record[field] = value

    with pytest.raises(collector.ValidationError, match=message):
        collector.validate_record(record)


def test_utc_now_iso_format() -> None:
    stamp = collector._utc_now_iso()

    assert stamp.endswith("Z")
    assert "T" in stamp


def test_main_writes_record_from_args(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collector, "_utc_now_iso", lambda: "2025-07-08T09:10:11Z")
    path = tmp_path / "metrics.ndjson"

    exit_code = collector.main(
        [
            "--path",
            str(path),
            "--pr-number",
            "44",
            "--iteration",
            "2",
            "--action",
            "retry",
            "--error-category",
            "none",
            "--duration-ms",
            "400",
            "--tasks-total",
            "10",
            "--tasks-complete",
            "7",
        ]
    )

    assert exit_code == 0
    lines = path.read_text(encoding="utf-8").splitlines()
    payload = collector.json.loads(lines[0])
    assert payload["timestamp"] == "2025-07-08T09:10:11Z"
    assert payload["tasks_complete"] == 7


def test_main_reports_missing_required_args(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = collector.main([])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "missing required field arguments" in captured.err


def test_main_handles_record_json_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "metrics.ndjson"
    exit_code = collector.main(["--path", str(path), "--record-json", "{"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "record_json must be valid JSON" in captured.err
