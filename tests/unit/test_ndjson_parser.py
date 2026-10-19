from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_read_ndjson_file_reports_bad_lines_and_accepts_objects(tmp_path: Path) -> None:
    path = tmp_path / "mixed.ndjson"
    path.write_text('{"first": 1}\nnot-json\n[]\n{"second": 2}\n', encoding="utf-8")

    entries, errors = ndjson_parser.read_ndjson_file(path)

    assert entries == [{"first": 1}, {"second": 2}]
    assert len(errors) == 2
    assert "invalid JSON" in errors[0]
    assert "expected object, got list" in errors[1]


def test_read_ndjson_file_falls_back_to_legacy_json_object_and_list(tmp_path: Path) -> None:
    object_path = tmp_path / "legacy-object.json"
    object_path.write_text('{\n  "legacy": true\n}\n', encoding="utf-8")
    list_path = tmp_path / "legacy-list.json"
    list_path.write_text('[\n {"one": 1},\n {"two": 2}\n]\n', encoding="utf-8")

    assert ndjson_parser.read_ndjson_file(object_path) == ([{"legacy": True}], [])
    assert ndjson_parser.read_ndjson_file(list_path) == ([{"one": 1}, {"two": 2}], [])


def test_read_ndjson_file_rejects_legacy_scalar_and_bounded_fallback(tmp_path: Path) -> None:
    scalar_path = tmp_path / "scalar.json"
    scalar_path.write_text("[1, 2]\n", encoding="utf-8")
    entries, errors = ndjson_parser.read_ndjson_file(scalar_path)
    assert entries == []
    assert errors

    bounded_path = tmp_path / "oversized.json"
    bounded_path.write_text("x" * (1024 * 1024 + 1), encoding="utf-8")
    entries, errors = ndjson_parser.read_ndjson_file(bounded_path)
    assert entries == []
    assert errors[-1].endswith("legacy-json-fallback-buffer-limit")


@pytest.mark.parametrize("prefix_count", [1, 3])
@pytest.mark.parametrize("invalid", ["not-json", "[]", "42"])
def test_read_ndjson_keeps_valid_prefix_before_malformed_line(
    tmp_path: Path, prefix_count: int, invalid: str
) -> None:
    prefix = [{"before": index} for index in range(prefix_count)]
    path = tmp_path / "history.ndjson"
    path.write_text(
        "\n".join([*(json.dumps(item) for item in prefix), invalid, '{"after": true}']) + "\n",
        encoding="utf-8",
    )

    entries, errors = ndjson_parser.read_ndjson_file(path)

    assert entries == [*prefix, {"after": True}]
    assert len(errors) == 1
    assert f":{prefix_count + 1}:" in errors[0]
