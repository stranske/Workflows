from __future__ import annotations

import pytest

from src import aggregator


def test_group_entries_handles_missing_and_extra_fields() -> None:
    entries = [
        {"metric_name": "latency", "workflow": "build", "dimension": "cpu", "value": 10},
        {"metric_name": "latency", "workflow": "build", "value": 20},
        {
            "metric_name": "throughput",
            "workflow": "deploy",
            "dimension": "cpu",
            "value": 30,
            "extra": "ignored",
        },
    ]

    grouped = aggregator.group_entries(entries, ["metric_name", "workflow", "dimension"])

    assert grouped[("latency", "build", "cpu")][0]["value"] == 10
    assert grouped[("latency", "build", "unknown")][0]["value"] == 20
    assert grouped[("throughput", "deploy", "cpu")][0]["value"] == 30


def test_build_grouped_aggregates_summary() -> None:
    entries = [
        {"metric_name": "latency", "workflow": "build", "dimension": "cpu", "value": 10},
        {"metric_name": "latency", "workflow": "build", "dimension": "cpu", "value": 30},
    ]

    aggregates = aggregator.build_grouped_aggregates(
        entries,
        numeric_fields=["value"],
        group_keys=["metric_name", "workflow", "dimension"],
    )

    assert len(aggregates) == 1
    aggregate = aggregates[0]
    assert aggregate["entry_type"] == "aggregate"
    assert aggregate["group"] == {
        "metric_name": "latency",
        "workflow": "build",
        "dimension": "cpu",
    }
    assert aggregate["summary"]["p50"] == pytest.approx(20.0)
