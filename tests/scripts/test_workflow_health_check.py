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


def test_load_workflow_runs_skips_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.ndjson"

    runs = workflow_health_check.load_workflow_runs(str(missing))

    assert runs == []


def test_load_workflow_runs_reads_nonempty_lines(tmp_path: Path) -> None:
    metrics_file = tmp_path / "metrics.ndjson"
    metrics_file.write_text(
        "\n".join(
            [
                json.dumps({"verdict": "pass"}),
                "",
                json.dumps({"status": "failure"}),
            ]
        )
        + "\n"
    )

    runs = workflow_health_check.load_workflow_runs(str(metrics_file))

    assert runs == [{"verdict": "pass"}, {"status": "failure"}]


def test_calculate_success_rate_uses_verdict_or_status() -> None:
    runs = [
        {"verdict": "pass"},
        {"status": "success"},
        {"verdict": "fail"},
        {"status": "failure"},
    ]

    assert workflow_health_check.calculate_success_rate(runs) == 50.0


def test_calculate_success_rate_empty() -> None:
    assert workflow_health_check.calculate_success_rate([]) == 0.0


def test_analyze_failure_patterns_counts_reasons() -> None:
    runs = [
        {"verdict": "pass"},
        {"verdict": "fail", "skip_reason": "flaky"},
        {"status": "failure", "error": "timeout"},
        {"status": "failure"},
        {"verdict": "fail", "skip_reason": "flaky"},
    ]

    patterns = workflow_health_check.analyze_failure_patterns(runs)

    assert patterns == {"flaky": 2, "timeout": 1, "unknown": 1}


def test_get_recent_runs_skips_older_runs() -> None:
    old_time = datetime(2000, 1, 1, tzinfo=UTC).isoformat()
    runs = [{"verdict": "pass", "recorded_at": old_time}]

    recent = workflow_health_check.get_recent_runs(runs, days=7)

    assert recent == []


def test_main_successful_run_prints_summary(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    metrics_file = tmp_path / "metrics.ndjson"
    metrics_file.write_text(
        json.dumps(
            {
                "verdict": "pass",
                "recorded_at": datetime.now(UTC).isoformat(),
            }
        )
        + "\n"
    )
    monkeypatch.setenv("METRICS_PATH", str(metrics_file))
    monkeypatch.setenv("SUCCESS_THRESHOLD", "80")

    workflow_health_check.main()

    captured = capsys.readouterr()
    assert "Workflow Health Report" in captured.out
    assert "Overall success rate: 100.0%" in captured.out


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
