from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import keepalive_metrics_collector as collector


def _sample_record() -> dict:
    return {
        "pr_number": 101,
        "iteration": 2,
        "timestamp": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
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
