"""Tests for the workflow health metrics report and its CLI."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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


def test_get_recent_runs_accepts_naive_timestamp() -> None:
    """Naive timestamps should be treated as UTC."""
    naive_time = datetime.now(UTC).replace(tzinfo=None).isoformat()
    runs = [{"verdict": "pass", "recorded_at": naive_time}]

    recent = workflow_health_check.get_recent_runs(runs, days=7)

    assert recent == runs


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
                "{not json}",
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


class TestLoadWorkflowRuns:
    """Tests for load_workflow_runs function."""

    def test_load_empty_file(self, tmp_path: Path) -> None:
        """Test loading an empty metrics file."""
        metrics_file = tmp_path / "metrics.ndjson"
        metrics_file.write_text("")

        runs = workflow_health_check.load_workflow_runs(str(metrics_file))
        assert runs == []

    def test_load_missing_file(self) -> None:
        """Test loading a non-existent file."""
        runs = workflow_health_check.load_workflow_runs("/nonexistent/path.ndjson")
        assert runs == []

    def test_load_valid_ndjson(self, tmp_path: Path) -> None:
        """Test loading valid NDJSON data."""
        metrics_file = tmp_path / "metrics.ndjson"
        metrics_file.write_text('{"verdict": "pass"}\n{"verdict": "fail"}\n')

        runs = workflow_health_check.load_workflow_runs(str(metrics_file))
        assert len(runs) == 2
        assert runs[0]["verdict"] == "pass"

    def test_load_skips_malformed_lines(self, tmp_path: Path) -> None:
        """Test malformed lines are skipped without crashing."""
        metrics_file = tmp_path / "metrics.ndjson"
        metrics_file.write_text('{"verdict": "pass"}\n{not-json}\n{"verdict": "fail"}\n')

        runs = workflow_health_check.load_workflow_runs(str(metrics_file))
        assert len(runs) == 2

    def test_load_with_path_object(self, tmp_path: Path) -> None:
        """Test loading with Path object instead of string - TYPE ERROR."""
        metrics_file = tmp_path / "metrics.ndjson"
        metrics_file.write_text('{"verdict": "pass"}\n')
        # Intentional type error: passing Path instead of str
        runs = workflow_health_check.load_workflow_runs(metrics_file)  # type: ignore[arg-type]
        assert len(runs) == 1


class TestCalculateSuccessRate:
    """Tests for calculate_success_rate function."""

    def test_empty_runs(self) -> None:
        """Test with empty run list."""
        assert workflow_health_check.calculate_success_rate([]) == 0.0

    def test_all_pass(self) -> None:
        """Test with all passing runs."""
        runs: list[dict[str, Any]] = [{"verdict": "pass"}, {"verdict": "pass"}]
        assert workflow_health_check.calculate_success_rate(runs) == 100.0

    def test_mixed_results(self) -> None:
        """Test with mixed pass/fail results."""
        runs: list[dict[str, Any]] = [
            {"verdict": "pass"},
            {"verdict": "fail"},
            {"status": "success"},
            {"status": "failure"},
        ]
        rate = workflow_health_check.calculate_success_rate(runs)
        assert rate == 50.0

    def test_single_failure(self) -> None:
        """Test with single failing run."""
        runs: list[dict[str, Any]] = [{"verdict": "fail"}]
        assert workflow_health_check.calculate_success_rate(runs) == 0.0

    def test_status_attribute(self) -> None:
        """Test success rate returned as float value."""
        runs: list[dict[str, Any]] = [{"verdict": "pass"}]
        rate = workflow_health_check.calculate_success_rate(runs)
        assert rate == 100.0


class TestAnalyzeFailurePatterns:
    """Tests for analyze_failure_patterns function."""

    def test_no_failures(self) -> None:
        """Test with no failing runs."""
        runs: list[dict[str, Any]] = [{"verdict": "pass"}]
        patterns = workflow_health_check.analyze_failure_patterns(runs)
        assert patterns == {}

    def test_grouped_failures(self) -> None:
        """Test that failures are grouped by reason."""
        runs: list[dict[str, Any]] = [
            {"verdict": "fail", "skip_reason": "token expired"},
            {"verdict": "fail", "skip_reason": "token expired"},
            {"verdict": "fail", "error": "timeout"},
        ]
        patterns = workflow_health_check.analyze_failure_patterns(runs)
        assert patterns["token expired"] == 2
        assert patterns["timeout"] == 1

    def test_unknown_reason(self) -> None:
        """Test failures without skip_reason or error."""
        runs: list[dict[str, Any]] = [{"verdict": "fail"}]
        patterns = workflow_health_check.analyze_failure_patterns(runs)
        # Failures without skip_reason or error should be counted under the "unknown" key
        assert patterns["unknown"] == 1


class TestGetRecentRuns:
    """Tests for get_recent_runs function."""

    def test_filters_old_runs(self) -> None:
        """Test that old runs are filtered out."""
        now = datetime.now(UTC)
        old_time = now.timestamp() - 30 * 86400  # 30 days ago
        recent_time = now.isoformat()

        runs: list[dict[str, Any]] = [
            {"verdict": "pass", "recorded_at": recent_time},
            {
                "verdict": "fail",
                "recorded_at": datetime.fromtimestamp(old_time, tz=UTC).isoformat(),
            },
        ]
        recent = workflow_health_check.get_recent_runs(runs, days=7)
        assert len(recent) == 1


class TestGenerateReport:
    """Tests for generate_report function."""

    def test_generates_report(self, tmp_path: Path) -> None:
        """Test that report contains expected fields."""
        metrics_file = tmp_path / "metrics.ndjson"
        metrics_file.write_text('{"verdict": "pass"}\n')

        report = workflow_health_check.generate_report(str(metrics_file))

        assert "total_runs" in report
        assert "overall_success_rate" in report
        assert report["total_runs"] == 1

    def test_generates_report_with_output(self, tmp_path: Path) -> None:
        """Test that report writes to output when requested."""
        metrics_file = tmp_path / "metrics.ndjson"
        metrics_file.write_text('{"verdict": "pass"}\n')
        output_path = tmp_path / "report.json"

        report = workflow_health_check.generate_report(str(metrics_file), str(output_path))

        assert output_path.exists()
        assert output_path.read_text(encoding="utf-8")
        assert report["total_runs"] == 1


class TestFormatDuration:
    """Tests for format_duration helper."""

    def test_format_duration_seconds(self) -> None:
        assert workflow_health_check.format_duration(42) == "42s"

    def test_format_duration_minutes(self) -> None:
        assert workflow_health_check.format_duration(75) == "1m 15s"

    def test_format_duration_hours(self) -> None:
        assert workflow_health_check.format_duration(3661) == "1h 1m"


class TestMain:
    """Tests for main CLI behavior."""

    def test_main_success(self, tmp_path: Path, capsys: Any, monkeypatch: Any) -> None:
        metrics_file = tmp_path / "metrics.ndjson"
        now = datetime.now(UTC).isoformat()
        metrics_file.write_text(f'{{"verdict": "pass", "recorded_at": "{now}"}}\n')
        output_path = tmp_path / "report.json"

        monkeypatch.setenv("METRICS_PATH", str(metrics_file))
        monkeypatch.setenv("OUTPUT_PATH", str(output_path))
        monkeypatch.setenv("SUCCESS_THRESHOLD", "50")

        workflow_health_check.main()

        captured = capsys.readouterr()
        assert "Workflow Health Report" in captured.out
        assert output_path.exists()

    def test_main_failure_threshold(self, tmp_path: Path, capsys: Any, monkeypatch: Any) -> None:
        metrics_file = tmp_path / "metrics.ndjson"
        now = datetime.now(UTC).isoformat()
        metrics_file.write_text(
            "\n".join(
                [
                    f'{{"verdict": "pass", "recorded_at": "{now}"}}',
                    f'{{"verdict": "fail", "recorded_at": "{now}"}}',
                ]
            )
            + "\n"
        )

        monkeypatch.setenv("METRICS_PATH", str(metrics_file))
        monkeypatch.setenv("SUCCESS_THRESHOLD", "90")

        with pytest.raises(SystemExit) as excinfo:
            workflow_health_check.main()

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "Warning: Recent success rate below" in captured.out
