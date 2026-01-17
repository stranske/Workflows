from pathlib import Path

from scripts import aggregate_repo_metrics as aggregator


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
