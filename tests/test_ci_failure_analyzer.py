"""Tests for ci_failure_analyzer module."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from scripts.ci_failure_analyzer import (
    aggregate_failures,
    classify_failure,
    generate_failure_report,
    get_recent_failures,
    identify_flaky_tests,
    load_failure_logs,
)


class TestLoadFailureLogs:
    """Tests for load_failure_logs function."""

    def test_load_empty_file(self, tmp_path: Path) -> None:
        """Test loading an empty log file."""
        log_file = tmp_path / "failures.ndjson"
        log_file.write_text("")

        logs = load_failure_logs(str(log_file))
        assert logs == []

    def test_load_missing_file(self) -> None:
        """Test loading a non-existent file."""
        logs = load_failure_logs("/nonexistent/path.ndjson")
        assert logs == []

    def test_load_valid_ndjson(self, tmp_path: Path) -> None:
        """Test loading valid NDJSON data."""
        log_file = tmp_path / "failures.ndjson"
        log_file.write_text('{"error": "timeout"}\n' '{"error": "assertion failed"}\n')

        logs = load_failure_logs(str(log_file))
        assert len(logs) == 2
        assert logs[0]["error"] == "timeout"

    def test_load_with_invalid_lines(self, tmp_path: Path) -> None:
        """Test loading file with some invalid JSON lines."""
        log_file = tmp_path / "failures.ndjson"
        log_file.write_text('{"error": "valid"}\n' "not valid json\n" '{"error": "also valid"}\n')

        logs = load_failure_logs(str(log_file))
        # Should skip invalid line and load valid ones
        assert len(logs) == 2


class TestClassifyFailure:
    """Tests for classify_failure function."""

    def test_classify_flaky_timeout(self) -> None:
        """Test that timeout errors are classified as flaky."""
        result = classify_failure("Request timeout exceeded")
        assert result == "flaky"

    def test_classify_flaky_connection(self) -> None:
        """Test that connection errors are classified as flaky."""
        result = classify_failure("Connection refused by server")
        assert result == "flaky"

    def test_classify_infrastructure_disk(self) -> None:
        """Test that disk space errors are infrastructure."""
        result = classify_failure("No disk space left on device")
        assert result == "infrastructure"

    def test_classify_infrastructure_memory(self) -> None:
        """Test that OOM errors are infrastructure."""
        result = classify_failure("Out of memory error")
        assert result == "infrastructure"

    def test_classify_test_assertion(self) -> None:
        """Test that assertion errors are test failures."""
        result = classify_failure("AssertionError: expected 5 got 4")
        assert result == "test"

    def test_classify_unknown(self) -> None:
        """Test that unrecognized errors are unknown."""
        result = classify_failure("Something completely different")
        assert result == "unknown"


class TestAggregateFailures:
    """Tests for aggregate_failures function."""

    def test_aggregate_empty(self) -> None:
        """Test aggregating empty failure list."""
        result = aggregate_failures([])
        assert result == {}

    def test_aggregate_mixed_failures(self) -> None:
        """Test aggregating failures of different types."""
        failures: List[Dict[str, Any]] = [
            {"error": "timeout exceeded"},
            {"error": "timeout exceeded"},
            {"error": "assertion failed"},
            {"error": "disk space"},
        ]

        result = aggregate_failures(failures)
        assert result["flaky"] == 2
        assert result["test"] == 1
        assert result["infrastructure"] == 1


class TestIdentifyFlakyTests:
    """Tests for identify_flaky_tests function."""

    def test_identify_no_flaky(self) -> None:
        """Test when no tests are flaky (all pass or all fail)."""
        failures: List[Dict[str, Any]] = [
            {"test_name": "test_a", "verdict": "pass"},
            {"test_name": "test_a", "verdict": "pass"},
            {"test_name": "test_b", "verdict": "fail"},
            {"test_name": "test_b", "verdict": "fail"},
        ]

        flaky = identify_flaky_tests(failures)
        assert flaky == []

    def test_identify_flaky_test(self) -> None:
        """Test identifying a flaky test."""
        failures: List[Dict[str, Any]] = [
            {"test_name": "test_flaky", "verdict": "pass"},
            {"test_name": "test_flaky", "verdict": "fail"},
            {"test_name": "test_flaky", "verdict": "pass"},
            {"test_name": "test_flaky", "verdict": "fail"},
        ]

        flaky = identify_flaky_tests(failures, threshold=0.3)
        assert "test_flaky" in flaky

    def test_identify_with_threshold(self) -> None:
        """Test that threshold affects flaky detection."""
        # 2 pass, 1 fail = 33% failure rate
        failures: List[Dict[str, Any]] = [
            {"test_name": "test_a", "verdict": "pass"},
            {"test_name": "test_a", "verdict": "pass"},
            {"test_name": "test_a", "verdict": "fail"},
        ]

        # Should be flaky at 0.3 threshold
        assert "test_a" in identify_flaky_tests(failures, threshold=0.3)
        # Should NOT be flaky at 0.5 threshold
        assert "test_a" not in identify_flaky_tests(failures, threshold=0.5)


class TestGenerateFailureReport:
    """Tests for generate_failure_report function."""

    def test_report_empty_failures(self) -> None:
        """Test report generation with no failures."""
        report = generate_failure_report([])
        assert "No failures" in report

    def test_report_text_format(self) -> None:
        """Test text format report generation."""
        failures: List[Dict[str, Any]] = [
            {"error": "timeout", "test_name": "test_a", "verdict": "fail"},
        ]

        report = generate_failure_report(failures, output_format="text")
        assert "CI Failure Report" in report
        assert "flaky" in report

    def test_report_markdown_format(self) -> None:
        """Test markdown format report generation."""
        failures: List[Dict[str, Any]] = [
            {"error": "timeout", "test_name": "test_a", "verdict": "fail"},
        ]

        report = generate_failure_report(failures, output_format="markdown")
        assert "# CI Failure Report" in report
        assert "**flaky**" in report


class TestGetRecentFailures:
    """Tests for get_recent_failures function."""

    def test_filter_recent_only(self) -> None:
        """Test filtering to recent failures only."""
        now = datetime.now(timezone.utc)
        recent_ts = now.isoformat()
        old_ts = "2020-01-01T00:00:00+00:00"

        failures: List[Dict[str, Any]] = [
            {"error": "recent", "timestamp": recent_ts},
            {"error": "old", "timestamp": old_ts},
        ]

        recent = get_recent_failures(failures, days=7)
        assert len(recent) == 1
        assert recent[0]["error"] == "recent"

    def test_handle_missing_timestamp(self) -> None:
        """Test handling records without timestamp."""
        failures: List[Dict[str, Any]] = [
            {"error": "no timestamp"},
            {"error": "with ts", "timestamp": datetime.now(timezone.utc).isoformat()},
        ]

        recent = get_recent_failures(failures, days=7)
        # Only the one with valid timestamp should be included
        assert len(recent) == 1


# ============================================================================
# INTENTIONAL TEST FAILURES for autofix validation
# ============================================================================


class TestIntentionalFailures:
    """Tests with intentional failures to test autofix error handling."""

    def test_assertion_failure(self) -> None:
        """Test with intentional assertion failure - AUTOFIX CANNOT FIX."""
        result = classify_failure("some error")
        # Wrong assertion - this will fail
        assert result == "this_is_wrong"

    def test_attribute_error(self) -> None:
        """Test with intentional attribute error - AUTOFIX CANNOT FIX."""
        result = "a string"
        # Strings don't have .nonexistent_method()
        assert result.nonexistent_method() == "test"  # type: ignore[attr-defined]

    def test_key_error(self) -> None:
        """Test with intentional key error - AUTOFIX CANNOT FIX."""
        data: Dict[str, int] = {"a": 1, "b": 2}
        # Key "missing" doesn't exist
        value = data["missing"]
        assert value == 1
