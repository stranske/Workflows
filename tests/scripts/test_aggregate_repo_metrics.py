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


def test_read_repo_metrics_files_accumulates_errors(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.ndjson"
    metrics.write_text('{"duration_ms": 10}\n', encoding="utf-8")
    missing = tmp_path / "missing.ndjson"

    entries, errors = aggregator.read_repo_metrics_files(
        [("alpha/one", metrics), ("beta/two", missing)]
    )

    assert errors == 1
    assert entries == [{"duration_ms": 10, "repo": "alpha/one"}]


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


def test_build_summary_comparisons_group_by_field() -> None:
    entries = [
        {"repo": "alpha", "duration_ms": 10, "size": 5},
        {"repo": "alpha", "duration_ms": 20},
        {"repo": "beta", "duration_ms": 30, "size": "ignored"},
        {"repo": "beta", "size": 15},
    ]

    summary = aggregator.build_summary(entries, errors=0, numeric_fields=["duration_ms", "size"])

    duration = summary["comparisons"]["duration_ms"]
    assert duration["overall"]["mean"] == pytest.approx(20.0)
    assert duration["repos"]["alpha"]["count"] == 2
    assert duration["repos"]["beta"]["summary"]["mean"] == pytest.approx(30.0)

    size = summary["comparisons"]["size"]
    assert size["repos"]["alpha"]["summary"]["mean"] == pytest.approx(5.0)
    assert size["repos"]["beta"]["count"] == 1


def test_build_summary_includes_missing_repo_names() -> None:
    entries = [
        {"repo": "alpha", "duration_ms": 10},
        {"repo": "alpha", "duration_ms": 20},
    ]

    summary = aggregator.build_summary(
        entries,
        errors=0,
        numeric_fields=["duration_ms"],
        repo_names=["alpha", "beta"],
    )

    assert summary["repos"]["beta"]["count"] == 0
    assert summary["repos"]["beta"]["aggregates"]["duration_ms"]["mean"] is None
    assert summary["comparisons"]["duration_ms"]["repos"]["beta"]["count"] == 0
    assert summary["comparisons"]["duration_ms"]["repos"]["beta"]["summary"]["mean"] is None


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


def test_parse_repo_specs_supports_csv_and_file(tmp_path: Path) -> None:
    repos_file = tmp_path / "repos.txt"
    repos_file.write_text("alpha/one # note\n# comment\nbeta/two\n", encoding="utf-8")
    metrics_dir = tmp_path / "metrics"

    specs = aggregator._parse_repo_specs(
        repo_specs=[" gamma/three = custom.ndjson "],
        repos_csv="delta/four",
        repos_file=repos_file,
        metrics_dir=metrics_dir,
    )

    spec_map = dict(specs)
    assert spec_map["alpha/one"] == metrics_dir / "alpha__one.ndjson"
    assert spec_map["beta/two"] == metrics_dir / "beta__two.ndjson"
    assert spec_map["delta/four"] == metrics_dir / "delta__four.ndjson"
    assert spec_map["gamma/three"] == Path("custom.ndjson")


def test_main_writes_outputs_for_repo_list(tmp_path: Path) -> None:
    metrics_dir = tmp_path / "metrics"
    metrics_dir.mkdir()
    (metrics_dir / "alpha__one.ndjson").write_text('{"duration_ms": 10}\n', encoding="utf-8")
    (metrics_dir / "beta__two.ndjson").write_text(
        '{"duration_ms": 20}\nnot-json\n', encoding="utf-8"
    )
    output = tmp_path / "out" / "combined.ndjson"
    summary_output = tmp_path / "out" / "summary.json"

    result = aggregator.main(
        [
            "--repos",
            "alpha/one,beta/two",
            "--metrics-dir",
            str(metrics_dir),
            "--output",
            str(output),
            "--summary-output",
            str(summary_output),
        ]
    )

    assert result == 0
    combined_entries = [
        json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()
    ]
    assert {entry["repo"] for entry in combined_entries} == {"alpha/one", "beta/two"}

    summary = json.loads(summary_output.read_text(encoding="utf-8"))
    assert summary["parse_errors"] == 1
    assert summary["overall"]["aggregates"]["duration_ms"]["mean"] == pytest.approx(15.0)
    assert summary["repos"]["alpha/one"]["count"] == 1


def test_main_reports_missing_repos(capsys: pytest.CaptureFixture[str]) -> None:
    result = aggregator.main([])

    assert result == 1
    captured = capsys.readouterr()
    assert "aggregate_repo_metrics: no repos specified." in captured.err
