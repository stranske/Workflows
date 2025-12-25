"""Tests for workflow_health_check module."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from scripts.workflow_health_check import (
    analyze_failure_patterns,
    calculate_success_rate,
    generate_report,
    get_recent_runs,
    load_workflow_runs,
)


class TestLoadWorkflowRuns:
    """Tests for load_workflow_runs function."""

    def test_load_empty_file(self, tmp_path: Path) -> None:
        """Test loading an empty metrics file."""
        metrics_file = tmp_path / "metrics.ndjson"
        metrics_file.write_text("")

        runs = load_workflow_runs(str(metrics_file))
        assert runs == []

    def test_load_missing_file(self) -> None:
        """Test loading a non-existent file."""
        runs = load_workflow_runs("/nonexistent/path.ndjson")
        assert runs == []

    def test_load_valid_ndjson(self, tmp_path: Path) -> None:
        """Test loading valid NDJSON data."""
        metrics_file = tmp_path / "metrics.ndjson"
        metrics_file.write_text('{"verdict": "pass"}\n{"verdict": "fail"}\n')

        runs = load_workflow_runs(str(metrics_file))
        assert len(runs) == 2
        assert runs[0]["verdict"] == "pass"

    def test_load_with_path_object(self, tmp_path: Path) -> None:
        """Test loading with Path object instead of string - TYPE ERROR."""
        metrics_file = tmp_path / "metrics.ndjson"
        metrics_file.write_text('{"verdict": "pass"}\n')
        # Intentional type error: passing Path instead of str
        runs = load_workflow_runs(metrics_file)  # type: ignore[arg-type]
        assert len(runs) == 1


class TestCalculateSuccessRate:
    """Tests for calculate_success_rate function."""

    def test_empty_runs(self) -> None:
        """Test with empty run list."""
        assert calculate_success_rate([]) == 0.0

    def test_all_pass(self) -> None:
        """Test with all passing runs."""
        runs: List[Dict[str, Any]] = [{"verdict": "pass"}, {"verdict": "pass"}]
        assert calculate_success_rate(runs) == 100.0

    def test_mixed_results(self) -> None:
        """Test with mixed pass/fail results."""
        runs: List[Dict[str, Any]] = [
            {"verdict": "pass"},
            {"verdict": "fail"},
            {"status": "success"},
            {"status": "failure"},
        ]
        rate = calculate_success_rate(runs)
        assert rate == 50.0

    def test_single_failure(self) -> None:
        """Test with single failing run."""
        runs: List[Dict[str, Any]] = [{"verdict": "fail"}]
        assert calculate_success_rate(runs) == 0.0

    def test_status_attribute(self) -> None:
        """Test success rate returned as float value."""
        runs: List[Dict[str, Any]] = [{"verdict": "pass"}]
        rate = calculate_success_rate(runs)
        assert rate == 100.0


class TestAnalyzeFailurePatterns:
    """Tests for analyze_failure_patterns function."""

    def test_no_failures(self) -> None:
        """Test with no failing runs."""
        runs: List[Dict[str, Any]] = [{"verdict": "pass"}]
        patterns = analyze_failure_patterns(runs)
        assert patterns == {}

    def test_grouped_failures(self) -> None:
        """Test that failures are grouped by reason."""
        runs: List[Dict[str, Any]] = [
            {"verdict": "fail", "skip_reason": "token expired"},
            {"verdict": "fail", "skip_reason": "token expired"},
            {"verdict": "fail", "error": "timeout"},
        ]
        patterns = analyze_failure_patterns(runs)
        assert patterns["token expired"] == 2
        assert patterns["timeout"] == 1

    def test_unknown_reason(self) -> None:
        """Test failures without skip_reason or error."""
        runs: List[Dict[str, Any]] = [{"verdict": "fail"}]
        patterns = analyze_failure_patterns(runs)
        # Failures without skip_reason or error should be counted under the "unknown" key
        assert patterns["unknown"] == 1


class TestGetRecentRuns:
    """Tests for get_recent_runs function."""

    def test_filters_old_runs(self) -> None:
        """Test that old runs are filtered out."""
        now = datetime.now(timezone.utc)
        old_time = now.timestamp() - 30 * 86400  # 30 days ago
        recent_time = now.isoformat()

        runs: List[Dict[str, Any]] = [
            {"verdict": "pass", "recorded_at": recent_time},
            {
                "verdict": "fail",
                "recorded_at": datetime.fromtimestamp(old_time, tz=timezone.utc).isoformat(),
            },
        ]
        recent = get_recent_runs(runs, days=7)
        assert len(recent) == 1


class TestGenerateReport:
    """Tests for generate_report function."""

    def test_generates_report(self, tmp_path: Path) -> None:
        """Test that report contains expected fields."""
        metrics_file = tmp_path / "metrics.ndjson"
        metrics_file.write_text('{"verdict": "pass"}\n')

        report = generate_report(str(metrics_file))

        assert "total_runs" in report
        assert "overall_success_rate" in report
        assert report["total_runs"] == 1
