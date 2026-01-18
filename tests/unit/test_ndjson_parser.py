from __future__ import annotations

from pathlib import Path

from src import ndjson_parser


def test_parse_ndjson_handles_blank_malformed_and_mixed_schema() -> None:
    lines = [
        "",
        "  ",
        '{"ok": 1}',
        "not-json",
        "42",
        '{"ok": 2, "extra": "value"}',
    ]

    entries, errors = ndjson_parser.parse_ndjson_lines(lines, source="metrics.ndjson")

    assert entries == [{"ok": 1}, {"ok": 2, "extra": "value"}]
    assert len(errors) == 2


def test_parse_ndjson_allows_missing_fields() -> None:
    lines = ['{"metric": "latency"}', '{"metric": "latency", "value": 12}']

    entries, errors = ndjson_parser.parse_ndjson_lines(lines)

    assert errors == []
    assert entries == [{"metric": "latency"}, {"metric": "latency", "value": 12}]


def test_read_ndjson_file_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing.ndjson"

    entries, errors = ndjson_parser.read_ndjson_file(missing)

    assert entries == []
    assert errors
