"""Tests for workflow_health_check module (scripts coverage)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts import workflow_health_check


def test_format_duration_branches() -> None:
    """Exercise short, minute, and hour duration formats."""
    assert workflow_health_check.format_duration(45) == "45s"
    assert workflow_health_check.format_duration(75) == "1m 15s"
    assert workflow_health_check.format_duration(3725) == "1h 2m"


def test_get_recent_runs_skips_invalid_timestamp() -> None:
    """Invalid timestamps should be ignored during recency filtering."""
    recent_time = datetime.now(UTC).isoformat()
    runs = [
        {"verdict": "pass", "recorded_at": recent_time},
        {"verdict": "fail", "recorded_at": "not-a-timestamp"},
        {"verdict": "pass", "recorded_at": ""},
    ]

    recent = workflow_health_check.get_recent_runs(runs, days=7)

    assert recent == [{"verdict": "pass", "recorded_at": recent_time}]


def test_generate_report_writes_output(tmp_path: Path) -> None:
    """Output file should be written when output_path is provided."""
    metrics_file = tmp_path / "metrics.ndjson"
    metrics_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "verdict": "pass",
                        "recorded_at": datetime.now(UTC).isoformat(),
                    }
                ),
                json.dumps(
                    {
                        "verdict": "fail",
                        "recorded_at": datetime.now(UTC).isoformat(),
                        "error": "timeout",
                    }
                ),
            ]
        )
        + "\n"
    )
    output_file = tmp_path / "report.json"

    report = workflow_health_check.generate_report(str(metrics_file), str(output_file))

    assert output_file.exists()
    saved = json.loads(output_file.read_text())
    assert saved["total_runs"] == 2
    assert saved == report


def test_main_exits_below_threshold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Main should exit non-zero when recent success rate is below threshold."""
    metrics_file = tmp_path / "metrics.ndjson"
    metrics_file.write_text(
        json.dumps(
            {
                "verdict": "fail",
                "recorded_at": datetime.now(UTC).isoformat(),
            }
        )
        + "\n"
    )
    monkeypatch.setenv("METRICS_PATH", str(metrics_file))
    monkeypatch.setenv("SUCCESS_THRESHOLD", "50")

    with pytest.raises(SystemExit) as excinfo:
        workflow_health_check.main()

    assert excinfo.value.code == 1
