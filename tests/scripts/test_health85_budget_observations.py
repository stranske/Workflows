"""Health 85 identity and issue #4284 trailing-seven-day p50 observations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.health85_budget_observations import (
    HEALTH85_PATH,
    build_observations,
    build_report,
    find_health85,
    report_json,
)

ROOT = Path(__file__).resolve().parents[2]
OBSERVATIONS_PATH = ROOT / "docs" / "evidence" / "issue-4284" / "health85-daily-observations.json"
REPORT_PATH = ROOT / "docs" / "reports" / "ci-budget.json"
REPORT_BLOB_SHA = "b917229e8f0cd9228754c6e30c4c0ef993dc0b99"


def _workflows() -> list[dict]:
    return [
        {
            "id": 301636189,
            "name": "Maint 85 Keepalive Durability Export",
            "path": ".github/workflows/maint-85-keepalive-durability-export.yml",
            "state": "active",
        },
        {
            "id": 387854305,
            "name": "Health 85 CI Time Budget",
            "path": HEALTH85_PATH,
            "state": "active",
        },
    ]


def test_find_health85_ignores_maint_85() -> None:
    found = find_health85(_workflows())
    assert found == {
        "id": 387854305,
        "name": "Health 85 CI Time Budget",
        "path": HEALTH85_PATH,
        "state": "active",
    }


def test_find_health85_rejects_a_missing_or_wrong_path() -> None:
    with pytest.raises(ValueError, match="expected one Health 85"):
        find_health85([])
    wrong = [
        {
            "id": 1,
            "name": "Health 85 CI Time Budget",
            "path": ".github/workflows/other.yml",
            "state": "active",
        }
    ]
    with pytest.raises(ValueError, match="Health 85 path"):
        find_health85(wrong)


def test_under_target_week_qualifies() -> None:
    rows = [
        {
            "date": f"2026-11-{day:02d}",
            "p50_minutes": 9.5,
            "run_id": 1000 + day,
            "run_conclusion": "success",
        }
        for day in range(1, 8)
    ]
    report = build_observations(rows)
    assert report["qualifying_seven_day_series"] is True
    assert report["failures"] == []
    assert report["observations"][0]["p50_seconds"] == 570.0
    assert report["observations"][0]["within_600_seconds"] is True


def test_gap_or_over_target_day_keeps_the_series_incomplete() -> None:
    rows = [
        {
            "date": f"2026-10-{day:02d}",
            "p50_minutes": 9.0,
            "run_id": day,
            "run_conclusion": "success",
        }
        for day in range(1, 7)
    ]
    rows.append(
        {
            "date": "2026-10-07",
            "p50_minutes": None,
            "run_id": 7,
            "run_conclusion": "failure",
        }
    )
    missing = build_observations(rows)
    assert missing["qualifying_seven_day_series"] is False
    assert "2026-10-07: p50 missing (measurement_unavailable)" in missing["failures"]

    rows[-1]["p50_minutes"] = 11.0
    slow = build_observations(rows)
    assert slow["qualifying_seven_day_series"] is False
    assert slow["observations"][-1]["p50_seconds"] == 660.0
    assert any("exceeds 600s" in failure for failure in slow["failures"])


def test_retained_health85_series_matches_observed_runs_and_does_not_qualify() -> None:
    rows = json.loads(OBSERVATIONS_PATH.read_text(encoding="utf-8"))
    report = build_report(
        _workflows(),
        rows,
        report_branch="ci-time-budget",
        report_blob_sha=REPORT_BLOB_SHA,
    )
    retained = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert report_json(report) == REPORT_PATH.read_text(encoding="utf-8")
    assert retained["source"]["workflow"]["id"] == 387854305
    assert retained["source"]["workflow"]["name"] == "Health 85 CI Time Budget"
    assert retained["qualifying_seven_day_series"] is False
    assert retained["p50_series_minutes"] == {
        "2026-10-31": 11.75,
        "2026-11-01": 11.716666666666665,
        "2026-11-02": 11.85,
        "2026-11-03": 11.841666666666667,
        "2026-11-04": 11.85,
        "2026-11-05": None,
        "2026-11-06": None,
    }
    urls = [row["source_run_url"] for row in retained["observations"]]
    assert urls[0] == "https://github.com/stranske/Workflows/actions/runs/41197692660"
    assert urls[-1] == "https://github.com/stranske/Workflows/actions/runs/42211705537"
    assert [row["status"] for row in retained["observations"][-2:]] == [
        "measurement_unavailable",
        "measurement_unavailable",
    ]
    assert all(
        row["p50_seconds"] is None or row["p50_seconds"] > 600 for row in retained["observations"]
    )
