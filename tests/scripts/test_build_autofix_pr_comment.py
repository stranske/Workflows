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
