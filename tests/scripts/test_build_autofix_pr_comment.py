"""Focused tests for :mod:`scripts.build_autofix_pr_comment`."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from scripts import build_autofix_pr_comment as autofix_comment


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_json_returns_none_for_missing_and_invalid_json(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.json"
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{not valid json", encoding="utf-8")

    assert autofix_comment.load_json(missing_path) is None
    assert autofix_comment.load_json(invalid_path) is None


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        (True, False, True),
        (False, True, False),
        (" true ", False, True),
        ("YES", False, True),
        ("on", False, True),
        ("1", False, True),
        (" false ", True, False),
        ("No", True, False),
        ("off", True, False),
        ("0", True, False),
        (2, False, True),
        (0, True, False),
        ("maybe", True, True),
        (None, True, True),
    ],
)
def test_coerce_bool_handles_edge_inputs(value: Any, default: bool, expected: bool) -> None:
    assert autofix_comment.coerce_bool(value, default=default) is expected


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        ("9", 0, 9),
        (" 010 ", 0, 10),
        (3.7, 0, 3),
        ("3.5", -1, -1),
        ("bad", 5, 5),
        (None, 7, 7),
    ],
)
def test_coerce_int_handles_edge_inputs(value: Any, default: int, expected: int) -> None:
    assert autofix_comment.coerce_int(value, default=default) == expected


def test_format_timestamp_contract_for_z_offsets_invalid_and_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return datetime(2026, 1, 2, 3, 4, 5, tzinfo=tz or UTC)

    monkeypatch.setattr(autofix_comment, "datetime", FrozenDateTime)

    assert autofix_comment.format_timestamp("2025-02-02T10:11:12Z") == ("2025-02-02 10:11:12 UTC")
    assert autofix_comment.format_timestamp("2025-02-02T05:11:12-05:00") == (
        "2025-02-02 10:11:12 UTC"
    )
    assert autofix_comment.format_timestamp("not-a-timestamp") == "not-a-timestamp"
    assert autofix_comment.format_timestamp(None) == "2026-01-02 03:04:05 UTC"


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        (None, (None, None)),
        ({"diagnostics": [{"code": "E001"}, {"code": "W002"}]}, (2, None)),
        ({"diagnostics": {"items": [{"code": "E001"}, {"code": "W002"}]}}, (2, None)),
        ({"diagnostics": {"count": "4"}}, (4, None)),
        ({"diagnostics_fixed": "3"}, (None, 3)),
        ({"classification": {"total": "5", "fixed": "2"}}, (5, 2)),
        (
            {
                "diagnostics": [],
                "diagnostics_fixed": "0",
                "classification": {"total": "5", "fixed": "2"},
            },
            (0, 0),
        ),
        (
            {
                "diagnostics": {"count": "many"},
                "diagnostics_fixed": "none",
                "classification": "invalid",
            },
            (None, None),
        ),
    ],
)
def test_extract_diagnostics_counts_handles_report_shapes(
    report: dict[str, Any] | None, expected: tuple[int | None, int | None]
) -> None:
    assert autofix_comment.extract_diagnostics_counts(report) == expected


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        (None, False),
        ({}, False),
        ({"diagnostics": []}, False),
        ({"diagnostics": [{"code": "E001"}]}, True),
        ({"diagnostics": {"count": "1"}}, True),
        ({"diagnostics_fixed": 1}, True),
        ({"classification": {"total": 0, "fixed": 2}}, True),
    ],
)
def test_should_emit_comment_for_no_detected_and_fixed_diagnostics(
    report: dict[str, Any] | None, expected: bool
) -> None:
    assert autofix_comment.should_emit_comment(report) is expected


def test_build_metadata_output_shape() -> None:
    assert autofix_comment.build_metadata(
        {"diagnostics": [{"code": "E001"}], "diagnostics_fixed": "2"}
    ) == {
        "diagnostics_count": 1,
        "diagnostics_fixed": 2,
        "should_post": True,
    }
    assert autofix_comment.build_metadata({"diagnostics": [], "diagnostics_fixed": 0}) == {
        "diagnostics_count": 0,
        "diagnostics_fixed": 0,
        "should_post": False,
    }


def test_extract_report_metadata_handles_missing_and_malformed_reports() -> None:
    assert autofix_comment.extract_report_metadata(None) == {
        "diagnostics_count": None,
        "diagnostics_fixed": None,
        "should_post": False,
    }
    assert autofix_comment.extract_report_metadata(
        {
            "diagnostics": {"count": "many"},
            "diagnostics_fixed": "none",
            "classification": "invalid",
        }
    ) == {
        "diagnostics_count": None,
        "diagnostics_fixed": None,
        "should_post": False,
    }
    assert (
        autofix_comment.render_status_line({"changed": "off", "classification": "not-a-dict"})
        == "Status | \u2705 no new diagnostics"
    )


def test_extract_report_metadata_handles_populated_report_shapes() -> None:
    report = {
        "diagnostics": {"items": [{"code": "E001"}, {"code": "W002"}]},
        "diagnostics_fixed_count": "1",
        "classification": {"new": "2"},
    }

    assert autofix_comment.extract_report_metadata(report) == {
        "diagnostics_count": 2,
        "diagnostics_fixed": 1,
        "should_post": True,
    }
    assert (
        autofix_comment.render_status_line(report)
        == "Status | \u26a0\ufe0f new diagnostics detected"
    )
    assert (
        autofix_comment.render_status_line({"changed": "true", "classification": {"new": 2}})
        == "Status | \u2705 autofix updates applied"
    )


def test_build_comment_handles_missing_report_and_trend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return datetime(2026, 1, 2, 3, 4, 5, tzinfo=tz or UTC)

    monkeypatch.setattr(autofix_comment, "datetime", FrozenDateTime)

    comment = autofix_comment.build_comment(
        report_path=tmp_path / "missing-report.json",
        trend_path=tmp_path / "missing-trend.json",
    )

    assert comment == "\n".join(
        [
            autofix_comment.MARKER,
            "Status | \u2705 no new diagnostics",
            "History points | 0",
            "Timestamp | 2026-01-02 03:04:05 UTC",
            "Report artifact | `autofix-report-pr-manual`",
            "Remaining | \u2205",
            "New | \u2205",
            "No additional artifacts",
            autofix_comment.MARKER,
        ]
    )


def test_build_comment_handles_malformed_report_classification(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    trend_path = tmp_path / "trend.json"
    _write_json(report_path, {"changed": False, "classification": ["invalid"]})
    _write_json(trend_path, {"remaining_latest": 0, "new_latest": 0})

    comment = autofix_comment.build_comment(report_path=report_path, trend_path=trend_path)

    lines = comment.splitlines()
    assert lines[1] == "Status | \u2705 no new diagnostics"
    assert lines[4] == "Report artifact | `autofix-report-pr-manual`"
    assert lines[5:] == [
        "Remaining | 0",
        "New | 0",
        "No additional artifacts",
        autofix_comment.MARKER,
    ]


def test_build_comment_changed_status_preserves_marker_and_artifact_name(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "report.json"
    trend_path = tmp_path / "trend.json"
    history_path = tmp_path / "history.json"
    _write_json(
        report_path,
        {
            "changed": True,
            "classification": {
                "new": 0,
                "timestamp": "2025-02-02T05:11:12-05:00",
            },
        },
    )
    _write_json(trend_path, {"remaining_latest": 0, "new_latest": 0})
    _write_json(history_path, [])

    comment = autofix_comment.build_comment(
        report_path=report_path,
        trend_path=trend_path,
        history_path=history_path,
        pr_number="42",
    )

    assert comment.count(autofix_comment.MARKER) == 2
    assert "Status | \u2705 autofix updates applied" in comment
    assert "Timestamp | 2025-02-02 10:11:12 UTC" in comment
    assert "Report artifact | `autofix-report-pr-42`" in comment
    assert "No additional artifacts" in comment


def test_build_comment_preserves_populated_markdown_line_order(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    trend_path = tmp_path / "trend.json"
    history_path = tmp_path / "history.json"
    _write_json(
        report_path,
        {
            "changed": False,
            "classification": {
                "total": 4,
                "new": 2,
                "timestamp": "2025-02-02T10:11:12+00:00",
                "by_code": {"W002": 1, "E001": 3},
            },
        },
    )
    _write_json(
        trend_path,
        {
            "remaining_latest": 4,
            "new_latest": 2,
            "codes": {"W002": {"latest": 1}, "E001": {"latest": 4}},
        },
    )
    _write_json(history_path, [{"remaining": 5}, {"remaining": 4}])

    comment = autofix_comment.build_comment(
        report_path=report_path,
        trend_path=trend_path,
        history_path=history_path,
        pr_number="101",
    )

    assert comment == "\n".join(
        [
            autofix_comment.MARKER,
            "Status | \u26a0\ufe0f new diagnostics detected",
            "History points | 2",
            "Timestamp | 2025-02-02 10:11:12 UTC",
            "Report artifact | `autofix-report-pr-101`",
            "Remaining | 4",
            "New | 2",
            "",
            "Top residual codes",
            "",
            "- `E001`: 4",
            "- `W002`: 1",
            "",
            "Current per-code counts",
            "",
            "- `E001`: 3",
            "- `W002`: 1",
            autofix_comment.MARKER,
        ]
    )


def test_cli_entrypoint_writes_comment_and_metadata_json(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    trend_path = tmp_path / "trend.json"
    history_path = tmp_path / "history.json"
    out_path = tmp_path / "out" / "autofix_pr_comment.md"
    metadata_path = tmp_path / "out" / "autofix_pr_comment.meta.json"
    _write_json(report_path, {"diagnostics": {"count": "2"}, "diagnostics_fixed": 1})
    _write_json(trend_path, {"remaining_latest": 2, "new_latest": 0})
    _write_json(history_path, [])

    assert (
        autofix_comment.main(
            [
                "--report",
                str(report_path),
                "--trend",
                str(trend_path),
                "--history",
                str(history_path),
                "--out",
                str(out_path),
                "--metadata-out",
                str(metadata_path),
                "--pr-number",
                "2617",
            ]
        )
        == 0
    )

    comment = out_path.read_text(encoding="utf-8")
    assert comment.count(autofix_comment.MARKER) == 2
    assert "Report artifact | `autofix-report-pr-2617`" in comment
    assert json.loads(metadata_path.read_text(encoding="utf-8")) == {
        "diagnostics_count": 2,
        "diagnostics_fixed": 1,
        "should_post": True,
    }


@pytest.mark.parametrize(
    ("report_content", "trend_content"),
    [
        ("{not valid json", None),
        (None, "{not valid json"),
    ],
)
def test_cli_entrypoint_tolerates_missing_or_malformed_inputs(
    tmp_path: Path, report_content: str | None, trend_content: str | None
) -> None:
    report_path = tmp_path / "report.json"
    trend_path = tmp_path / "trend.json"
    out_path = tmp_path / "out" / "autofix_pr_comment.md"
    metadata_path = tmp_path / "out" / "autofix_pr_comment.meta.json"
    if report_content is not None:
        report_path.write_text(report_content, encoding="utf-8")
    if trend_content is not None:
        trend_path.write_text(trend_content, encoding="utf-8")

    assert (
        autofix_comment.main(
            [
                "--report",
                str(report_path),
                "--trend",
                str(trend_path),
                "--out",
                str(out_path),
                "--metadata-out",
                str(metadata_path),
                "--pr-number",
                "2654",
            ]
        )
        == 0
    )

    comment = out_path.read_text(encoding="utf-8")
    assert "Status | \u2705 no new diagnostics" in comment
    assert "Report artifact | `autofix-report-pr-2654`" in comment
    assert "Remaining | \u2205" in comment
    assert "New | \u2205" in comment
    assert "No additional artifacts" in comment
    assert json.loads(metadata_path.read_text(encoding="utf-8")) == {
        "diagnostics_count": None,
        "diagnostics_fixed": None,
        "should_post": False,
    }
