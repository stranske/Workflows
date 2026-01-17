import json
from pathlib import Path

from scripts import autopilot_metrics_collector as collector


def test_append_record_creates_parent_dirs(tmp_path: Path) -> None:
    record = {
        "schema_version": collector.AUTOPILOT_METRICS_SCHEMA_VERSION,
        "metric_type": "cycle",
        "issue_number": 9,
        "timestamp": "2025-01-01T00:00:00Z",
        "cycle_count": 1,
    }
    nested_path = tmp_path / "nested" / "metrics" / "autopilot.ndjson"

    collector.append_record(nested_path, record)

    assert nested_path.exists()
    payload = json.loads(nested_path.read_text(encoding="utf-8").strip())
    collector.validate_record(payload)


def test_main_respects_env_log_path(tmp_path: Path, monkeypatch) -> None:
    log_path = tmp_path / "env" / "metrics.ndjson"
    monkeypatch.setenv("AUTOPILOT_METRICS_LOG_PATH", str(log_path))

    exit_code = collector.main(
        [
            "--metric-type",
            "cycle",
            "--issue-number",
            "5",
            "--cycle-count",
            "2",
        ]
    )

    assert exit_code == 0
    assert log_path.exists()
    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    collector.validate_record(payload)
