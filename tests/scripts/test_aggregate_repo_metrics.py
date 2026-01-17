import json
from pathlib import Path

import pytest

from scripts import aggregate_repo_metrics as aggregator


def test_summarize_values_empty() -> None:
    summary = aggregator.summarize_values([])

    assert summary == {"mean": None, "p50": None, "p90": None, "p99": None}


def test_summarize_values_percentiles() -> None:
    summary = aggregator.summarize_values([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

    assert summary["mean"] == pytest.approx(5.5)
    assert summary["p50"] == pytest.approx(5.5)
    assert summary["p90"] == pytest.approx(9.1)
    assert summary["p99"] == pytest.approx(9.91)


def test_aggregate_numeric_fields_filters_non_numeric() -> None:
    entries = [
        {"duration_ms": "10"},
        {"duration_ms": "not-a-number"},
        {"duration_ms": None},
        {"duration_ms": True},
        {"duration_ms": 20},
    ]

    aggregates = aggregator.aggregate_numeric_fields(entries, ["duration_ms"])

    summary = aggregates["duration_ms"]
    assert summary["mean"] == pytest.approx(15.0)
    assert summary["p50"] == pytest.approx(15.0)
    assert summary["p90"] == pytest.approx(19.0)
    assert summary["p99"] == pytest.approx(19.9)


def test_read_ndjson_handles_invalid_lines(tmp_path: Path) -> None:
    path = tmp_path / "metrics.ndjson"
    path.write_text('{"ok": 1}\nnot-json\n42\n{"ok": 2}\n', encoding="utf-8")

    entries, errors = aggregator._read_ndjson(path)

    assert entries == [{"ok": 1}, {"ok": 2}]
    assert errors == 2


def test_read_ndjson_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.ndjson"

    entries, errors = aggregator._read_ndjson(missing)

    assert entries == []
    assert errors == 1


def test_read_repo_metrics_tags_repo(tmp_path: Path) -> None:
    path = tmp_path / "metrics.ndjson"
    path.write_text('{"summary": {"tests": 10}}\n', encoding="utf-8")

    entries, errors = aggregator.read_repo_metrics(path, "owner/repo")

    assert errors == 0
    assert entries == [{"summary": {"tests": 10}, "repo": "owner/repo"}]


def test_infer_numeric_fields_ignores_repo_and_non_numeric() -> None:
    entries = [
        {"repo": "alpha", "duration_ms": "10", "note": "ok", "flag": True},
        {"repo": "beta", "duration_ms": None, "count": 2, "size": 1.5},
    ]

    fields = aggregator._infer_numeric_fields(entries)

    assert fields == ["count", "duration_ms", "size"]


def test_build_summary_groups_by_repo() -> None:
    entries = [
        {"repo": "alpha", "duration_ms": 10},
        {"repo": "alpha", "duration_ms": 20},
        {"repo": "beta", "duration_ms": 30},
    ]

    summary = aggregator.build_summary(entries, errors=1, numeric_fields=["duration_ms"])

    assert summary["parse_errors"] == 1
    assert summary["overall"]["aggregates"]["duration_ms"]["mean"] == pytest.approx(20.0)
    assert summary["repos"]["alpha"]["aggregates"]["duration_ms"]["mean"] == pytest.approx(15.0)
    assert summary["repos"]["beta"]["count"] == 1


def test_write_combined_ndjson(tmp_path: Path) -> None:
    entries = [
        {"repo": "alpha", "duration_ms": 10},
        {"repo": "beta", "duration_ms": 20},
    ]
    output = tmp_path / "combined.ndjson"

    aggregator.write_combined_ndjson(output, entries)

    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == entries[0]
    assert json.loads(lines[1]) == entries[1]
