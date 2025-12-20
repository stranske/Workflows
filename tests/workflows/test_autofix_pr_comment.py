"""Tests for :mod:`scripts.build_autofix_pr_comment`."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from scripts.build_autofix_pr_comment import (
    MARKER,
    _snapshot_code_lines,
    _top_code_lines,
    build_comment,
    coerce_bool,
    coerce_int,
    format_spark,
    format_timestamp,
    load_json,
    main,
)

pytestmark = pytest.mark.cosmetic


def test_load_json_and_coercion_helpers(tmp_path: Path) -> None:
    payload = {"value": 7}
    good = tmp_path / "report.json"
    good.write_text(json.dumps(payload), encoding="utf-8")

    missing = tmp_path / "missing.json"
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")

    assert load_json(good) == payload
    assert load_json(missing) is None
    assert load_json(corrupt) is None

    assert coerce_bool(True) is True
    assert coerce_bool("YES") is True
    assert coerce_bool("off") is False
    assert coerce_bool(0) is False

    assert coerce_int("9") == 9
    assert coerce_int("bad", default=5) == 5

    now = format_timestamp(None)
    # Basic sanity check – string parses back to a datetime.
    datetime.strptime(now, "%Y-%m-%d %H:%M:%S UTC")

    iso = format_timestamp("2025-01-02T03:04:05Z")
    assert iso == "2025-01-02 03:04:05 UTC"
    assert format_timestamp("not-a-timestamp") == "not-a-timestamp"

    assert format_spark("▁▂▃") == "▁▂▃"
    assert format_spark(()) == "∅"


def test_code_line_helpers_cover_all_branches() -> None:
    codes = {
        "E001": {"latest": "5", "spark": "▁▃▇"},
        "W002": {"latest": 1},
    }
    lines = _top_code_lines(codes)
    assert "Top residual codes" in "\n".join(lines)

    snapshot = {"E001": "3", "A000": 1}
    snap_lines = _snapshot_code_lines(snapshot)
    assert "Current per-code counts" in "\n".join(snap_lines)

    assert _top_code_lines(None) == ()
    assert _snapshot_code_lines({}) == ()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_comment_full_flow(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    history_path = tmp_path / "hist.json"
    trend_path = tmp_path / "trend.json"

    report_payload = {
        "changed": False,
        "classification": {
            "total": 4,
            "new": 2,
            "allowed": 1,
            "timestamp": "2025-02-02T10:11:12+00:00",
            "by_code": {"E001": 3, "W002": 1},
        },
    }
    history_payload: list[dict[str, int]] = [{"remaining": 4}, {"remaining": 3}]
    trend_payload = {
        "remaining_latest": 4,
        "new_latest": 2,
        "remaining_spark": "▁▂▃",
        "new_spark": "▁▃▇",
        "codes": {
            "E001": {"latest": 4, "spark": "▁▃"},
            "W002": {"latest": 1, "spark": "▂▃"},
        },
    }

    _write_json(report_path, report_payload)
    _write_json(history_path, list(history_payload))
    _write_json(trend_path, trend_payload)

    comment = build_comment(
        report_path=report_path,
        history_path=history_path,
        trend_path=trend_path,
        pr_number="42",
    )

    assert comment.count(MARKER) == 2
    assert "Status | ⚠️ new diagnostics detected" in comment
    assert "History points | 2" in comment
    assert "`autofix-report-pr-42`" in comment
    assert "Top residual codes" in comment
    assert "`E001`: 3" in comment


def test_build_comment_defaults_and_autofix_suffix(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    trend_path = tmp_path / "trend.json"

    _write_json(
        report_path,
        {
            "changed": True,
            "classification": {
                "total": 0,
                "new": 0,
                "allowed": 0,
                "timestamp": "invalid",  # triggers raw fallback
                "by_code": {},
            },
        },
    )
    _write_json(trend_path, {"remaining_latest": 0, "new_latest": 0})

    comment = build_comment(report_path=report_path, trend_path=trend_path)

    assert "autofix updates applied" in comment
    assert "invalid" in comment  # Timestamp fallback
    assert "No additional artifacts" in comment


def test_cli_entrypoint_writes_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = tmp_path / "report.json"
    trend = tmp_path / "trend.json"
    history = tmp_path / "history.json"
    out_path = tmp_path / "out" / "comment.md"

    _write_json(report, {"classification": {"total": 1, "new": 0, "allowed": 0}})
    _write_json(trend, {"remaining_latest": 0, "new_latest": 0})
    _write_json(history, [])

    exit_code = main(
        [
            "--report",
            str(report),
            "--trend",
            str(trend),
            "--history",
            str(history),
            "--out",
            str(out_path),
            "--pr-number",
            "7",
        ]
    )

    assert exit_code == 0
    assert out_path.exists()
    content = out_path.read_text()
    assert "autofix-report-pr-7" in content
