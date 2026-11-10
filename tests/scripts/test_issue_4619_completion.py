"""Issue #4619 completion stays unreconciled until both live-verification gates pass."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

from scripts.health85_budget_observations import HEALTH85_PATH, build_report, report_json
from scripts.issue_4619_completion import (
    DEFAULT_POST_CHANGE_RUN_ID,
    main,
    reconcile_completion,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "evidence" / "issue-4619"
OBSERVATIONS = EVIDENCE / "health85-daily-observations.json"
ISSUE_VIEW = EVIDENCE / "issue-view-4619.json"
GATE = EVIDENCE / "gate-run-42820421600.json"
BUDGET = EVIDENCE / "ci-budget-report.json"
DECISION = EVIDENCE / "completion-reconciliation.json"
REPORT_BLOB_SHA = "e3c490b336175e61a944bf30257e81eebcdac76b"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _qualifying_report() -> dict:
    observations = []
    for offset in range(7):
        day = date(2026, 11, 4) + timedelta(days=offset)
        run_id = 6000 + offset
        observations.append(
            {
                "date": day.isoformat(),
                "p50_seconds": 540.0,
                "source_run_url": f"https://github.com/stranske/Workflows/actions/runs/{run_id}",
            }
        )
    return {
        "qualifying_seven_day_series": True,
        "failures": [],
        "observations": observations,
    }


def _issue_for(report: dict, *, state: str = "OPEN", body_prefix: str = "") -> dict:
    lines = [body_prefix] if body_prefix else []
    for row in report["observations"]:
        seconds = row["p50_seconds"]
        rendered = "missing" if seconds is None else f"{float(seconds):.1f}"
        lines.append(f"| {row['date']} | 9.0 | {rendered} | yes | {row['source_run_url']} |")
    return {"state": state, "body": chr(10).join(lines), "comments": []}


def test_retained_health85_series_for_4619_matches_observed_runs_and_does_not_qualify() -> None:
    rows = json.loads(OBSERVATIONS.read_text(encoding="utf-8"))
    report = build_report(
        _workflows(),
        rows,
        report_branch="ci-time-budget",
        report_blob_sha=REPORT_BLOB_SHA,
        issue=4619,
    )
    retained = _load(BUDGET)
    assert report_json(report) == BUDGET.read_text(encoding="utf-8")
    assert retained["schema"] == "issue-4619-health85-observations/v1"
    assert retained["issue"] == 4619
    assert retained["source"]["workflow"]["id"] == 387854305
    assert retained["source"]["report_blob_sha"] == REPORT_BLOB_SHA
    assert retained["consecutive_calendar_dates"] is True
    assert retained["qualifying_seven_day_series"] is False
    assert retained["p50_series_minutes"] == {
        "2026-11-04": 11.85,
        "2026-11-05": None,
        "2026-11-06": None,
        "2026-11-07": None,
        "2026-11-08": None,
        "2026-11-09": None,
        "2026-11-10": 11.241666666666667,
    }


def test_retained_issue_view_leaves_4619_completion_unreconciled() -> None:
    issue = _load(ISSUE_VIEW)
    gate = _load(GATE)
    report = _load(BUDGET)
    decision = reconcile_completion(issue, gate, report, checked_on="2026-11-10")
    assert decision == _load(DECISION)
    assert decision["issue"] == 4619
    assert decision["state"] == "OPEN"
    assert decision["gate_run_id"] == DEFAULT_POST_CHANGE_RUN_ID
    assert decision["gate_run_supported"] is True
    assert decision["sustained_series_supported"] is False
    assert decision["both_gates_supported"] is False
    assert decision["completion_reconciled"] is False
    assert decision["action"] == "leave_incomplete"
    assert decision["issue_mutation"] == "none"
    assert decision["sustained_performance_criterion"] == "incomplete"
    assert "Issue state and acceptance checkboxes were left unchanged." in decision["comment"]
    assert "- [ ] Health 85 reports" in issue["body"]


def test_qualifying_series_can_be_reconciled_when_issue_4619_matches() -> None:
    report = _qualifying_report()
    decision = reconcile_completion(_issue_for(report), _load(GATE), report)
    assert decision["completion_reconciled"] is True
    assert decision["action"] == "mark_complete"
    assert decision["both_gates_supported"] is True
    assert decision["sustained_performance_criterion"] == "complete"
    assert decision["issue_mutation"] == "none"
    assert decision["failures"] == []


def test_checked_health85_box_without_evidence_is_recorded() -> None:
    report = _load(BUDGET)
    issue = _load(ISSUE_VIEW)
    issue["body"] = issue["body"].replace(
        "- [ ] Health 85 reports",
        "- [x] Health 85 reports",
        1,
    )
    decision = reconcile_completion(issue, _load(GATE), report)
    assert decision["completion_reconciled"] is False
    assert (
        "issue body checks the Health 85 gate without qualifying evidence" in decision["failures"]
    )


def test_failed_gate_blocks_qualifying_series() -> None:
    report = _qualifying_report()
    gate = deepcopy(_load(GATE))
    gate["passed"] = False
    gate["jobs"][0]["seconds"] = 700.0
    gate["jobs"][0]["within_limit"] = False
    decision = reconcile_completion(_issue_for(report), gate, report)
    assert decision["gate_run_supported"] is False
    assert decision["sustained_series_supported"] is True
    assert decision["completion_reconciled"] is False
    assert any("python ci / python 3.13" in failure for failure in decision["failures"])


def test_main_writes_the_retained_4619_decision(tmp_path: Path) -> None:
    output = tmp_path / "completion-reconciliation.json"
    code = main(
        [
            "--issue-view",
            str(ISSUE_VIEW),
            "--gate-evidence",
            str(GATE),
            "--budget",
            str(BUDGET),
            "--output",
            str(output),
            "--checked-on",
            "2026-11-10",
        ]
    )
    assert code == 0
    assert json.loads(output.read_text(encoding="utf-8")) == _load(DECISION)
