"""Tests for ci_failure_analyzer report formatting helpers."""

from typing import Any

from scripts.ci_failure_analyzer import (
    FLAKY_PATTERNS,
    INFRASTRUCTURE_PATTERNS,
    aggregate_failures,
    classify_failure,
    format_markdown_flaky_tests,
    format_markdown_summary,
    format_text_flaky_tests,
    format_text_summary,
    generate_failure_report,
    get_recent_failures,
    identify_flaky_tests,
    load_failure_logs,
)


class TestClassifyFailure:
    """Tests for classify_failure function - preserved behavior."""

    def test_classify_flaky_timeout(self) -> None:
        """Test that timeout errors are classified as flaky."""
        result = classify_failure("Request timeout exceeded")
        assert result == "flaky"

    def test_classify_flaky_connection_refused(self) -> None:
        """Test that connection refused errors are classified as flaky."""
        result = classify_failure("Connection refused by server")
        assert result == "flaky"

    def test_classify_flaky_rate_limit(self) -> None:
        """Test that rate limit errors are classified as flaky."""
        result = classify_failure("Rate limit exceeded")
        assert result == "flaky"

    def test_classify_infrastructure_disk_space(self) -> None:
        """Test that disk space errors are infrastructure."""
        result = classify_failure("No disk space left on device")
        assert result == "infrastructure"

    def test_classify_infrastructure_memory(self) -> None:
        """Test that OOM errors are infrastructure."""
        result = classify_failure("Out of memory error")
        assert result == "infrastructure"

    def test_classify_infrastructure_network_unreachable(self) -> None:
        """Test that network unreachable errors are infrastructure."""
        result = classify_failure("Network unreachable")
        assert result == "infrastructure"

    def test_classify_test_assertion(self) -> None:
        """Test that assertion errors are test failures."""
        result = classify_failure("AssertionError: expected 5 got 4")
        assert result == "test"

    def test_classify_test_assert(self) -> None:
        """Test that assert errors are test failures."""
        result = classify_failure("Assert failed")
        assert result == "test"

    def test_classify_test_exception(self) -> None:
        """Test that exception errors are test failures."""
        result = classify_failure("Exception occurred")
        assert result == "test"

    def test_classify_test_error(self) -> None:
        """Test that error messages are test failures."""
        result = classify_failure("Error in test")
        assert result == "test"

    def test_classify_unknown(self) -> None:
        """Test that unrecognized errors are unknown."""
        result = classify_failure("Something completely different")
        assert result == "unknown"


class TestAggregateFailures:
    """Tests for aggregate_failures function - preserved behavior."""

    def test_aggregate_empty(self) -> None:
        """Test aggregating empty failure list."""
        result = aggregate_failures([])
        assert result == {}

    def test_aggregate_all_flaky(self) -> None:
        """Test aggregating all flaky failures."""
        failures: list[dict[str, Any]] = [
            {"error": "timeout exceeded"},
            {"error": "connection refused"},
        ]
        result = aggregate_failures(failures)
        assert result == {"flaky": 2}

    def test_aggregate_all_infrastructure(self) -> None:
        """Test aggregating all infrastructure failures."""
        failures: list[dict[str, Any]] = [
            {"error": "out of memory"},
            {"error": "disk space"},
        ]
        result = aggregate_failures(failures)
        assert result == {"infrastructure": 2}

    def test_aggregate_mixed_failures(self) -> None:
        """Test aggregating failures of different types."""
        failures: list[dict[str, Any]] = [
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
    """Tests for identify_flaky_tests function - preserved behavior."""

    def test_identify_no_flaky(self) -> None:
        """Test when no tests are flaky (all pass or all fail)."""
        failures: list[dict[str, Any]] = [
            {"test_name": "test_a", "verdict": "pass"},
            {"test_name": "test_a", "verdict": "pass"},
            {"test_name": "test_b", "verdict": "fail"},
            {"test_name": "test_b", "verdict": "fail"},
        ]

        flaky = identify_flaky_tests(failures)
        assert flaky == []

    def test_identify_flaky_test(self) -> None:
        """Test identifying a flaky test."""
        failures: list[dict[str, Any]] = [
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
        failures: list[dict[str, Any]] = [
            {"test_name": "test_a", "verdict": "pass"},
            {"test_name": "test_a", "verdict": "pass"},
            {"test_name": "test_a", "verdict": "fail"},
        ]

        # Should be flaky at 0.3 threshold
        assert "test_a" in identify_flaky_tests(failures, threshold=0.3)
        # Should NOT be flaky at 0.5 threshold
        assert "test_a" not in identify_flaky_tests(failures, threshold=0.5)

    def test_identify_skips_empty_or_unknown_verdicts(self) -> None:
        """Test that missing names and unknown verdicts are ignored."""
        failures: list[dict[str, Any]] = [
            {"test_name": "", "verdict": "pass"},
            {"test_name": "test_unknown", "verdict": "skipped"},
            {"test_name": "test_known", "verdict": "pass"},
            {"test_name": "test_known", "verdict": "fail"},
        ]

        flaky = identify_flaky_tests(failures, threshold=0.4)
        assert flaky == ["test_known"]

    def test_identify_multiple_flaky_tests(self) -> None:
        """Test identifying multiple flaky tests."""
        failures: list[dict[str, Any]] = [
            {"test_name": "test_a", "verdict": "pass"},
            {"test_name": "test_a", "verdict": "fail"},
            {"test_name": "test_b", "verdict": "pass"},
            {"test_name": "test_b", "verdict": "fail"},
        ]

        flaky = identify_flaky_tests(failures, threshold=0.3)
        assert "test_a" in flaky
        assert "test_b" in flaky


class TestFormatTextSummary:
    """Tests for format_text_summary helper function."""

    def test_format_empty_aggregated(self) -> None:
        """Test formatting empty aggregated results."""
        lines = format_text_summary({})
        assert lines == ["Summary:"]

    def test_format_single_classification(self) -> None:
        """Test formatting single classification."""
        aggregated = {"flaky": 5}
        lines = format_text_summary(aggregated)
        assert "Summary:" in lines
        assert "  flaky: 5" in lines

    def test_format_multiple_classifications(self) -> None:
        """Test formatting multiple classifications."""
        aggregated = {"flaky": 5, "test": 3, "infrastructure": 2}
        lines = format_text_summary(aggregated)
        assert lines[0] == "Summary:"
        # Should be sorted alphabetically
        assert "  flaky: 5" in lines
        assert "  infrastructure: 2" in lines
        assert "  test: 3" in lines


class TestFormatTextFlakyTests:
    """Tests for format_text_flaky_tests helper function."""

    def test_format_empty_flaky(self) -> None:
        """Test formatting empty flaky tests list."""
        lines = format_text_flaky_tests([])
        assert lines == []

    def test_format_single_flaky_test(self) -> None:
        """Test formatting single flaky test."""
        lines = format_text_flaky_tests(["test_a"])
        assert lines[0] == "Flaky Tests:"
        assert "  - test_a" in lines

    def test_format_multiple_flaky_tests(self) -> None:
        """Test formatting multiple flaky tests."""
        lines = format_text_flaky_tests(["test_a", "test_b"])
        assert lines[0] == "Flaky Tests:"
        assert "  - test_a" in lines
        assert "  - test_b" in lines


class TestFormatMarkdownSummary:
    """Tests for format_markdown_summary helper function."""

    def test_format_empty_aggregated(self) -> None:
        """Test formatting empty aggregated results."""
        lines = format_markdown_summary({})
        assert lines == ["## Summary", ""]

    def test_format_single_classification(self) -> None:
        """Test formatting single classification."""
        aggregated = {"flaky": 5}
        lines = format_markdown_summary(aggregated)
        assert "## Summary" in lines
        assert "- **flaky**: 5" in lines

    def test_format_multiple_classifications(self) -> None:
        """Test formatting multiple classifications."""
        aggregated = {"flaky": 5, "test": 3, "infrastructure": 2}
        lines = format_markdown_summary(aggregated)
        assert lines[0] == "## Summary"
        # Should be sorted alphabetically
        assert "- **flaky**: 5" in lines
        assert "- **infrastructure**: 2" in lines
        assert "- **test**: 3" in lines


class TestFormatMarkdownFlakyTests:
    """Tests for format_markdown_flaky_tests helper function."""

    def test_format_empty_flaky(self) -> None:
        """Test formatting empty flaky tests list."""
        lines = format_markdown_flaky_tests([])
        assert lines == []

    def test_format_single_flaky_test(self) -> None:
        """Test formatting single flaky test."""
        lines = format_markdown_flaky_tests(["test_a"])
        assert lines[0] == "## Flaky Tests"
        assert "- `test_a`" in lines

    def test_format_multiple_flaky_tests(self) -> None:
        """Test formatting multiple flaky tests."""
        lines = format_markdown_flaky_tests(["test_a", "test_b"])
        assert lines[0] == "## Flaky Tests"
        assert "- `test_a`" in lines
        assert "- `test_b`" in lines


class TestGenerateFailureReport:
    """Tests for generate_failure_report function - preserved behavior."""

    def test_report_empty_failures(self) -> None:
        """Test report generation with no failures."""
        report = generate_failure_report([])
        assert "No failures" in report

    def test_report_text_format(self) -> None:
        """Test text format report generation."""
        failures: list[dict[str, Any]] = [
            {"error": "timeout", "test_name": "test_a", "verdict": "fail"},
        ]

        report = generate_failure_report(failures, output_format="text")
        assert "CI Failure Report" in report
        assert "flaky" in report

    def test_report_markdown_format(self) -> None:
        """Test markdown format report generation."""
        failures: list[dict[str, Any]] = [
            {"error": "timeout", "test_name": "test_a", "verdict": "fail"},
        ]

        report = generate_failure_report(failures, output_format="markdown")
        assert "# CI Failure Report" in report
        assert "**flaky**" in report

    def test_report_text_includes_flaky_tests(self) -> None:
        """Test text format report with flaky tests section."""
        failures: list[dict[str, Any]] = [
            {"error": "timeout", "test_name": "test_flaky", "verdict": "pass"},
            {"error": "timeout", "test_name": "test_flaky", "verdict": "fail"},
        ]

        report = generate_failure_report(failures, output_format="text")
        assert "Flaky Tests:" in report
        assert "test_flaky" in report

    def test_report_markdown_includes_flaky_tests(self) -> None:
        """Test markdown format report with flaky tests section."""
        failures: list[dict[str, Any]] = [
            {"error": "timeout", "test_name": "test_flaky", "verdict": "pass"},
            {"error": "timeout", "test_name": "test_flaky", "verdict": "fail"},
        ]

        report = generate_failure_report(failures, output_format="markdown")
        assert "## Flaky Tests" in report
        assert "`test_flaky`" in report

    def test_report_text_no_flaky_section_when_none(self) -> None:
        """Test text format report without flaky section when no flaky tests."""
        failures: list[dict[str, Any]] = [
            {"error": "timeout", "test_name": "test_a", "verdict": "fail"},
            {"error": "timeout", "test_name": "test_a", "verdict": "fail"},
        ]

        report = generate_failure_report(failures, output_format="text")
        assert "Flaky Tests:" not in report

    def test_report_markdown_no_flaky_section_when_none(self) -> None:
        """Test markdown format report without flaky section when no flaky tests."""
        failures: list[dict[str, Any]] = [
            {"error": "timeout", "test_name": "test_a", "verdict": "fail"},
            {"error": "timeout", "test_name": "test_a", "verdict": "fail"},
        ]

        report = generate_failure_report(failures, output_format="markdown")
        assert "## Flaky Tests" not in report

    def test_report_text_summary_counts(self) -> None:
        """Test text format report includes correct summary counts."""
        failures: list[dict[str, Any]] = [
            {"error": "timeout"},
            {"error": "timeout"},
            {"error": "assertion failed"},
            {"error": "disk space"},
        ]

        report = generate_failure_report(failures, output_format="text")
        assert "flaky: 2" in report
        assert "test: 1" in report
        assert "infrastructure: 1" in report

    def test_report_markdown_summary_counts(self) -> None:
        """Test markdown format report includes correct summary counts."""
        failures: list[dict[str, Any]] = [
            {"error": "timeout"},
            {"error": "timeout"},
            {"error": "assertion failed"},
            {"error": "disk space"},
        ]

        report = generate_failure_report(failures, output_format="markdown")
        assert "**flaky**: 2" in report
        assert "**test**: 1" in report
        assert "**infrastructure**: 1" in report


class TestLoadFailureLogs:
    """Tests for load_failure_logs function - preserved behavior."""

    def test_load_empty_file(self, tmp_path: Any) -> None:
        """Test loading an empty log file."""
        from pathlib import Path

        log_file: Path = tmp_path / "failures.ndjson"
        log_file.write_text("")

        logs = load_failure_logs(str(log_file))
        assert logs == []

    def test_load_missing_file(self) -> None:
        """Test loading a non-existent file."""
        logs = load_failure_logs("/nonexistent/path.ndjson")
        assert logs == []

    def test_load_valid_ndjson(self, tmp_path: Any) -> None:
        """Test loading valid NDJSON data."""
        from pathlib import Path

        log_file: Path = tmp_path / "failures.ndjson"
        log_file.write_text('{"error": "timeout"}\n{"error": "assertion failed"}\n')

        logs = load_failure_logs(str(log_file))
        assert len(logs) == 2
        assert logs[0]["error"] == "timeout"

    def test_load_with_invalid_lines(self, tmp_path: Any) -> None:
        """Test loading file with some invalid JSON lines."""
        from pathlib import Path

        log_file: Path = tmp_path / "failures.ndjson"
        log_file.write_text('{"error": "valid"}\nnot valid json\n{"error": "also valid"}\n')

        logs = load_failure_logs(str(log_file))
        # Should skip invalid line and load valid ones
        assert len(logs) == 2


class TestGetRecentFailures:
    """Tests for get_recent_failures function - preserved behavior."""

    def test_filter_recent_only(self) -> None:
        """Test filtering to recent failures only."""
        from datetime import datetime, timezone

        # Python 3.11+ has datetime.UTC, but we need to support 3.9+
        try:
            from datetime import UTC
        except ImportError:
            UTC = timezone.utc  # noqa: UP017 - fallback for Python < 3.11

        now = datetime.now(UTC)
        recent_ts = now.isoformat()
        old_ts = "2020-01-01T00:00:00+00:00"

        failures: list[dict[str, Any]] = [
            {"error": "recent", "timestamp": recent_ts},
            {"error": "old", "timestamp": old_ts},
        ]

        recent = get_recent_failures(failures, days=7)
        assert len(recent) == 1
        assert recent[0]["error"] == "recent"

    def test_handle_missing_timestamp(self) -> None:
        """Test handling records without timestamp."""
        from datetime import datetime, timezone

        # Python 3.11+ has datetime.UTC, but we need to support 3.9+
        try:
            from datetime import UTC
        except ImportError:
            UTC = timezone.utc  # noqa: UP017 - fallback for Python < 3.11

        failures: list[dict[str, Any]] = [
            {"error": "no timestamp"},
            {"error": "with ts", "timestamp": datetime.now(UTC).isoformat()},
        ]

        recent = get_recent_failures(failures, days=7)
        # Only the one with valid timestamp should be included
        assert len(recent) == 1

    def test_handle_invalid_timestamp_values(self) -> None:
        """Test handling invalid timestamp values."""
        from datetime import datetime, timezone

        # Python 3.11+ has datetime.UTC, but we need to support 3.9+
        try:
            from datetime import UTC
        except ImportError:
            UTC = timezone.utc  # noqa: UP017 - fallback for Python < 3.11

        now = datetime.now(UTC).isoformat()
        failures: list[dict[str, Any]] = [
            {"error": "bad format", "timestamp": "not-a-timestamp"},
            {"error": "bad type", "timestamp": 123},
            {"error": "good", "timestamp": now},
        ]

        recent = get_recent_failures(failures, days=7)
        assert len(recent) == 1
        assert recent[0]["error"] == "good"


class TestPatternConstants:
    """Tests for pattern constants to ensure they remain unchanged."""

    def test_flaky_patterns_exist(self) -> None:
        """Test that flaky patterns are defined."""
        assert FLAKY_PATTERNS is not None
        assert len(FLAKY_PATTERNS) > 0

    def test_infrastructure_patterns_exist(self) -> None:
        """Test that infrastructure patterns are defined."""
        assert INFRASTRUCTURE_PATTERNS is not None
        assert len(INFRASTRUCTURE_PATTERNS) > 0

    def test_flaky_patterns_types(self) -> None:
        """Test that flaky patterns are strings."""
        for pattern in FLAKY_PATTERNS:
            assert isinstance(pattern, str)

    def test_infrastructure_patterns_types(self) -> None:
        """Test that infrastructure patterns are strings."""
        for pattern in INFRASTRUCTURE_PATTERNS:
            assert isinstance(pattern, str)
