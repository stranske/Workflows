"""Tests for scripts/aggregate_metrics.py"""

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from scripts.aggregate_metrics import aggregate_metrics, format_json, format_report


def write_ndjson(path: Path, records: list[dict[str, Any]]) -> None:
    """Helper to write NDJSON test data."""
    path.write_text("\n".join(json.dumps(r) for r in records))


def test_aggregate_metrics_empty_file(tmp_path: Path) -> None:
    """Test handling of empty metrics file."""
    empty_file = tmp_path / "empty.ndjson"
    empty_file.write_text("")

    summary = aggregate_metrics(empty_file)

    assert summary["total_operations"] == 0
    assert summary["operations_with_trace"] == 0
    assert summary["trace_coverage_percent"] == 0.0
    assert summary["by_operation"] == {}
    assert summary["by_step"] == {}


def test_aggregate_metrics_missing_file() -> None:
    """Test handling of nonexistent file."""
    with pytest.raises(FileNotFoundError):
        aggregate_metrics(Path("/nonexistent/file.ndjson"))


def test_aggregate_metrics_valid_ndjson(tmp_path: Path) -> None:
    """Test aggregation with valid NDJSON input."""
    metrics_file = tmp_path / "metrics.ndjson"
    write_ndjson(
        metrics_file,
        [
            {"metric_type": "api_call", "trace_id": "trace-1"},
            {"metric_type": "api_call", "trace_id": None},
            {"metric_type": "workflow", "trace_id": "trace-2"},
            {"metric_type": "workflow"},  # No trace_id field
        ],
    )

    summary = aggregate_metrics(metrics_file)

    assert summary["total_operations"] == 4
    assert summary["operations_with_trace"] == 2
    assert summary["trace_coverage_percent"] == 50.0
    assert summary["by_operation"]["api_call"] == {
        "total": 2,
        "with_trace": 1,
        "coverage_percent": 50.0,
    }
    assert summary["by_operation"]["workflow"] == {
        "total": 2,
        "with_trace": 1,
        "coverage_percent": 50.0,
    }


def test_aggregate_metrics_autopilot_steps(tmp_path: Path) -> None:
    """Test grouping by autopilot step_name."""
    metrics_file = tmp_path / "metrics.ndjson"
    write_ndjson(
        metrics_file,
        [
            {"metric_type": "autopilot", "step_name": "format", "trace_id": "t1"},
            {"metric_type": "autopilot", "step_name": "format", "trace_id": "t2"},
            {"metric_type": "autopilot", "step_name": "optimize"},
            {"metric_type": "autopilot", "step_name": "apply", "trace_id": "t3"},
        ],
    )

    summary = aggregate_metrics(metrics_file)

    assert summary["by_step"]["format"] == {
        "total": 2,
        "with_trace": 2,
        "coverage_percent": 100.0,
    }
    assert summary["by_step"]["optimize"] == {
        "total": 1,
        "with_trace": 0,
        "coverage_percent": 0.0,
    }
    assert summary["by_step"]["apply"] == {
        "total": 1,
        "with_trace": 1,
        "coverage_percent": 100.0,
    }


def test_aggregate_metrics_missing_fields(tmp_path: Path) -> None:
    """Test handling of records missing metric_type or step_name."""
    metrics_file = tmp_path / "metrics.ndjson"
    write_ndjson(
        metrics_file,
        [
            {"trace_id": "t1"},  # No metric_type
            {"metric_type": "autopilot", "trace_id": "t2"},  # No step_name
        ],
    )

    summary = aggregate_metrics(metrics_file)

    assert summary["by_operation"]["unknown"] == {
        "total": 1,
        "with_trace": 1,
        "coverage_percent": 100.0,
    }
    assert summary["by_step"]["unknown"] == {
        "total": 1,
        "with_trace": 1,
        "coverage_percent": 100.0,
    }


def test_aggregate_metrics_division_by_zero(tmp_path: Path) -> None:
    """Test coverage calculation when total is zero (shouldn't happen, but test defense)."""
    # This scenario is prevented by the empty file case, but test the summary structure
    metrics_file = tmp_path / "metrics.ndjson"
    write_ndjson(metrics_file, [])

    summary = aggregate_metrics(metrics_file)

    assert summary["trace_coverage_percent"] == 0.0
    assert summary["by_operation"] == {}
    assert summary["by_step"] == {}


def test_format_json() -> None:
    """Test JSON formatting output."""
    summary = {
        "total_operations": 10,
        "operations_with_trace": 8,
        "trace_coverage_percent": 80.0,
        "by_operation": {
            "api_call": {"total": 5, "with_trace": 4, "coverage_percent": 80.0}
        },
        "by_step": {"format": {"total": 3, "with_trace": 3, "coverage_percent": 100.0}},
    }

    output = format_json(summary)

    parsed = json.loads(output)
    assert parsed["total_operations"] == 10
    assert parsed["trace_coverage_percent"] == 80.0


def test_format_report() -> None:
    """Test markdown report formatting."""
    summary = {
        "total_operations": 10,
        "operations_with_trace": 8,
        "trace_coverage_percent": 80.0,
        "by_operation": {
            "api_call": {"total": 5, "with_trace": 4, "coverage_percent": 80.0}
        },
        "by_step": {"format": {"total": 3, "with_trace": 3, "coverage_percent": 100.0}},
    }

    output = format_report(summary)

    assert "# LangSmith Trace Coverage Report" in output
    assert "**Overall:** 80.0%" in output
    assert "| api_call |" in output
    assert "| format |" in output
    assert "80.0%" in output
    assert "100.0%" in output


def test_format_report_empty_groups() -> None:
    """Test report formatting when operation/step groups are empty."""
    summary = {
        "total_operations": 0,
        "operations_with_trace": 0,
        "trace_coverage_percent": 0.0,
        "by_operation": {},
        "by_step": {},
    }

    output = format_report(summary)

    assert "# LangSmith Trace Coverage Report" in output
    assert "**Overall:** 0.0%" in output
    # Should not contain operation/step tables
    assert "## Coverage by Operation" not in output
    assert "## Coverage by Autopilot Step" not in output


def test_invalid_json_lines(tmp_path: Path) -> None:
    """Test handling of malformed JSON in NDJSON file."""
    metrics_file = tmp_path / "invalid.ndjson"
    metrics_file.write_text('{"valid": true}\n{invalid json}\n{"also_valid": true}')

    with pytest.raises(json.JSONDecodeError):
        aggregate_metrics(metrics_file)
