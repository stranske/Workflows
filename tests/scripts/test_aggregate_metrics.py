"""Tests for scripts/aggregate_metrics.py"""

import json
from pathlib import Path
from typing import Any

from scripts.aggregate_metrics import aggregate_traces, format_report, load_metrics


def write_ndjson(path: Path, records: list[dict[str, Any]]) -> None:
    """Helper to write NDJSON test data."""
    path.write_text("\n".join(json.dumps(r) for r in records))


def test_load_metrics_empty_file(tmp_path: Path) -> None:
    """Test handling of empty metrics file."""
    empty_file = tmp_path / "empty.ndjson"
    empty_file.write_text("")

    metrics = load_metrics(empty_file)

    assert metrics == []


def test_load_metrics_missing_file(tmp_path: Path) -> None:
    """Test handling of nonexistent file."""
    nonexistent = tmp_path / "nonexistent.ndjson"
    metrics = load_metrics(nonexistent)
    assert metrics == []


def test_load_metrics_valid_ndjson(tmp_path: Path) -> None:
    """Test loading valid NDJSON input."""
    metrics_file = tmp_path / "metrics.ndjson"
    write_ndjson(
        metrics_file,
        [
            {"metric_type": "api_call", "langsmith_trace_id": "trace-1"},
            {"metric_type": "workflow", "langsmith_trace_id": "trace-2"},
        ],
    )

    metrics = load_metrics(metrics_file)

    assert len(metrics) == 2
    assert metrics[0]["metric_type"] == "api_call"
    assert metrics[1]["metric_type"] == "workflow"


def test_load_metrics_invalid_json_lines(tmp_path: Path) -> None:
    """Test handling of malformed JSON in NDJSON file."""
    metrics_file = tmp_path / "invalid.ndjson"
    metrics_file.write_text('{"valid": true}\n{invalid json}\n{"also_valid": true}')

    # Should skip invalid lines and continue
    metrics = load_metrics(metrics_file)

    assert len(metrics) == 2
    assert metrics[0] == {"valid": True}
    assert metrics[1] == {"also_valid": True}


def test_aggregate_traces_empty_metrics() -> None:
    """Test aggregation with empty metrics list."""
    summary = aggregate_traces([])

    assert summary["total_metrics"] == 0
    assert summary["total_with_traces"] == 0
    assert summary["trace_coverage_pct"] == 0.0
    assert summary["by_operation"] == {}
    assert summary["by_step"] == {}


def test_aggregate_traces_with_traces() -> None:
    """Test aggregation with metrics containing traces."""
    metrics = [
        {"metric_type": "api_call", "langsmith_trace_id": "trace-1"},
        {"metric_type": "api_call", "langsmith_trace_id": None},
        {"metric_type": "workflow", "langsmith_trace_id": "trace-2"},
        {"metric_type": "workflow"},  # No langsmith_trace_id field
    ]

    summary = aggregate_traces(metrics)

    assert summary["total_metrics"] == 4
    assert summary["total_with_traces"] == 2
    assert summary["trace_coverage_pct"] == 50.0
    assert summary["by_operation"]["api_call"] == {
        "total": 2,
        "with_trace": 1,
        "coverage_pct": 50.0,
    }
    assert summary["by_operation"]["workflow"] == {
        "total": 2,
        "with_trace": 1,
        "coverage_pct": 50.0,
    }


def test_aggregate_traces_with_trace_lists() -> None:
    """Test aggregation with compare-mode trace lists."""
    metrics = [
        {
            "metric_type": "evaluation",
            "langsmith_traces": [
                {"provider": "openai", "trace_id": "trace-1"},
                {"provider": "anthropic", "trace_id": "trace-2"},
            ],
        },
        {"metric_type": "evaluation", "langsmith_traces": []},
    ]

    summary = aggregate_traces(metrics)

    assert summary["total_metrics"] == 2
    assert summary["total_with_traces"] == 1
    assert summary["trace_coverage_pct"] == 50.0
    assert summary["by_operation"]["evaluation"] == {
        "total": 2,
        "with_trace": 1,
        "coverage_pct": 50.0,
    }


def test_aggregate_traces_autopilot_steps() -> None:
    """Test grouping by autopilot step_name."""
    metrics = [
        {
            "metric_type": "autopilot",
            "step_name": "format",
            "langsmith_trace_id": "t1",
        },
        {
            "metric_type": "autopilot",
            "step_name": "format",
            "langsmith_trace_id": "t2",
        },
        {"metric_type": "autopilot", "step_name": "optimize"},
        {
            "metric_type": "autopilot",
            "step_name": "apply",
            "langsmith_trace_id": "t3",
        },
    ]

    summary = aggregate_traces(metrics)

    assert summary["by_step"]["format"] == {
        "total": 2,
        "with_trace": 2,
        "coverage_pct": 100.0,
    }
    assert summary["by_step"]["optimize"] == {
        "total": 1,
        "with_trace": 0,
        "coverage_pct": 0.0,
    }
    assert summary["by_step"]["apply"] == {
        "total": 1,
        "with_trace": 1,
        "coverage_pct": 100.0,
    }


def test_aggregate_traces_missing_fields() -> None:
    """Test handling of records missing metric_type or step_name."""
    metrics = [
        {"langsmith_trace_id": "t1"},  # No metric_type
        {
            "metric_type": "autopilot",
            "langsmith_trace_id": "t2",
        },  # No step_name
    ]

    summary = aggregate_traces(metrics)

    # First metric has unknown operation type
    assert summary["by_operation"]["unknown"] == {
        "total": 1,
        "with_trace": 1,
        "coverage_pct": 100.0,
    }
    # Both metrics lack step_name, so both go to "unknown" step
    assert summary["by_step"]["unknown"] == {
        "total": 2,
        "with_trace": 2,
        "coverage_pct": 100.0,
    }


def test_format_report() -> None:
    """Test markdown report formatting."""
    summary = {
        "total_metrics": 10,
        "total_with_traces": 8,
        "trace_coverage_pct": 80.0,
        "by_operation": {"api_call": {"total": 5, "with_trace": 4, "coverage_pct": 80.0}},
        "by_step": {"format": {"total": 3, "with_trace": 3, "coverage_pct": 100.0}},
    }

    output = format_report(summary)

    assert "# LangSmith Trace Coverage Report" in output
    assert "Coverage: 80.0%" in output
    assert "| api_call |" in output
    assert "| format |" in output
    assert "80.0%" in output
    assert "100.0%" in output


def test_format_report_empty_groups() -> None:
    """Test report formatting when operation/step groups are empty."""
    summary = {
        "total_metrics": 0,
        "total_with_traces": 0,
        "trace_coverage_pct": 0.0,
        "by_operation": {},
        "by_step": {},
    }

    output = format_report(summary)

    assert "# LangSmith Trace Coverage Report" in output
    assert "Coverage: 0.0%" in output
    # Should not contain operation/step tables
    assert "## Coverage by Operation" not in output
    assert "## Coverage by Autopilot Step" not in output


def test_end_to_end(tmp_path: Path) -> None:
    """Test full pipeline: load → aggregate → format."""
    metrics_file = tmp_path / "metrics.ndjson"
    write_ndjson(
        metrics_file,
        [
            {"metric_type": "api", "langsmith_trace_id": "t1"},
            {"metric_type": "api"},
            {"metric_type": "workflow", "langsmith_trace_id": "t2"},
        ],
    )

    metrics = load_metrics(metrics_file)
    summary = aggregate_traces(metrics)
    report = format_report(summary)

    assert len(metrics) == 3
    assert summary["total_metrics"] == 3
    assert summary["total_with_traces"] == 2
    assert summary["trace_coverage_pct"] == 66.7
    assert "Coverage: 66.7%" in report
