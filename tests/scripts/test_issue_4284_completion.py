"""Issue #4284 completion stays unreconciled until both live-verification gates pass."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

from scripts.issue_4284_completion import main, reconcile_completion

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "evidence" / "issue-4284"
ISSUE_VIEW = EVIDENCE / "issue-view-4284.json"
GATE = EVIDENCE / "gate-run-40551187519.json"
BUDGET = ROOT / "docs" / "reports" / "ci-budget.json"
DECISION = EVIDENCE / "completion-reconciliation.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _qualifying_report() -> dict:
    observations = []
    for offset in range(7):
        day = date(2026, 11, 1) + timedelta(days=offset)
        run_id = 5000 + offset
        observations.append(
            {
                "date": day.isoformat(),
                "p50_seconds": 570.0,
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
        lines.append(f"| {row['date']} | 9.5 | {rendered} | yes | {row['source_run_url']} |")
    return {"state": state, "body": "\n".join(lines), "comments": []}


def test_retained_issue_view_leaves_completion_unreconciled() -> None:
    issue = _load(ISSUE_VIEW)
    gate = _load(GATE)
    report = _load(BUDGET)
    decision = reconcile_completion(issue, gate, report, checked_on="2026-11-06")
    assert decision == _load(DECISION)
    assert decision["state"] == "CLOSED"
    assert decision["comment_count"] == 24
    assert decision["followup_issue"] == 4482
    assert decision["gate_run_supported"] is True
    assert decision["sustained_series_supported"] is False
    assert decision["observations_match_issue"] is True
    assert decision["both_gates_supported"] is False
    assert decision["completion_reconciled"] is False
    assert decision["action"] == "leave_incomplete"
    assert decision["issue_mutation"] == "none"
    assert decision["sustained_performance_criterion"] == "incomplete"
    assert decision["matched_dates"] == [
        "2026-10-31",
        "2026-11-01",
        "2026-11-02",
        "2026-11-03",
        "2026-11-04",
        "2026-11-05",
        "2026-11-06",
    ]
    assert decision["failures"] == report["failures"]
    assert "Issue state and acceptance checkboxes were left unchanged." in decision["comment"]
    assert "- [ ] Live-verification gate: Health 85 reports" in issue["body"]


def test_qualifying_series_can_be_reconciled_when_the_issue_matches() -> None:
    report = _qualifying_report()
    decision = reconcile_completion(_issue_for(report), _load(GATE), report)
    assert decision["completion_reconciled"] is True
    assert decision["action"] == "mark_complete"
    assert decision["both_gates_supported"] is True
    assert decision["sustained_performance_criterion"] == "complete"
    assert decision["issue_mutation"] == "none"
    assert decision["failures"] == []


def test_qualifying_series_without_matching_issue_text_stays_incomplete() -> None:
    report = _qualifying_report()
    issue = _issue_for(report)
    issue["body"] = issue["body"].replace("570.0", "999.0", 1)
    decision = reconcile_completion(issue, _load(GATE), report)
    assert decision["sustained_series_supported"] is True
    assert decision["observations_match_issue"] is False
    assert decision["completion_reconciled"] is False
    assert decision["action"] == "leave_incomplete"
    assert decision["sustained_performance_criterion"] == "incomplete"
    assert any("no matching Health 85 p50 line" in failure for failure in decision["failures"])


def test_true_flag_with_an_over_limit_day_does_not_qualify() -> None:
    report = _qualifying_report()
    report["observations"][-1]["p50_seconds"] = 705.0
    decision = reconcile_completion(_issue_for(report), _load(GATE), report)
    assert decision["sustained_series_supported"] is False
    assert decision["completion_reconciled"] is False
    assert any("exceeds 600s" in failure for failure in decision["failures"])


def test_checked_health85_box_without_evidence_is_recorded() -> None:
    report = _load(BUDGET)
    issue = _load(ISSUE_VIEW)
    issue["body"] = issue["body"].replace(
        "- [ ] Live-verification gate: Health 85 reports",
        "- [x] Live-verification gate: Health 85 reports",
        1,
    )
    decision = reconcile_completion(issue, _load(GATE), report)
    assert decision["completion_reconciled"] is False
    assert (
        "issue body checks the Health 85 gate without qualifying evidence" in decision["failures"]
    )


def test_failed_gate_blocks_a_qualifying_series() -> None:
    report = _qualifying_report()
    gate = deepcopy(_load(GATE))
    gate["passed"] = False
    gate["jobs"][1]["seconds"] = 700
    gate["jobs"][1]["within_limit"] = False
    decision = reconcile_completion(_issue_for(report), gate, report)
    assert decision["gate_run_supported"] is False
    assert decision["sustained_series_supported"] is True
    assert decision["completion_reconciled"] is False
    assert any("python ci / python 3.14" in failure for failure in decision["failures"])


def test_main_writes_the_retained_decision(tmp_path: Path) -> None:
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
            "2026-11-06",
        ]
    )
    assert code == 0
    assert json.loads(output.read_text(encoding="utf-8")) == _load(DECISION)


def test_main_rejects_a_non_object_issue_view(tmp_path: Path) -> None:
    issue = tmp_path / "issue.json"
    issue.write_text("[]\n", encoding="utf-8")
    output = tmp_path / "out.json"
    code = main(
        [
            "--issue-view",
            str(issue),
            "--gate-evidence",
            str(GATE),
            "--budget",
            str(BUDGET),
            "--output",
            str(output),
        ]
    )
    assert code == 1
    assert not output.exists()
