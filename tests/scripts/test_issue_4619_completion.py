"""Issue #4619 completion stays unreconciled until both live-verification gates pass."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from scripts.health85_budget_observations import HEALTH85_PATH, build_report, report_json
from scripts.issue_4619_completion import (
    DEFAULT_POST_CHANGE_RUN_ID,
    DEFAULT_PRE_CHANGE_RUN_ID,
    compare_before_after_gate_runs,
    evaluate_native_daily_observations,
    gate_run_supported,
    main,
    reconcile_completion,
    verify_native_daily_observations_match,
    verify_published_ci_budget_alignment,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "evidence" / "issue-4619"
OBSERVATIONS = EVIDENCE / "health85-daily-observations.json"
ISSUE_VIEW = EVIDENCE / "issue-view-4619.json"
PRE_GATE = EVIDENCE / "gate-run-41771220527.json"
GATE = EVIDENCE / "gate-run-42820421600.json"
BUDGET = EVIDENCE / "ci-budget-report.json"
DECISION = EVIDENCE / "completion-reconciliation.json"
REPORT_BLOB_SHA = "f06d6f3fd0aa301b320cece179f97a8ef3c02aa7"


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
        "2026-11-10": 11.133333333333333,
    }


def test_retained_issue_view_leaves_4619_completion_unreconciled() -> None:
    issue = _load(ISSUE_VIEW)
    gate = _load(GATE)
    report = _load(BUDGET)
    decision = reconcile_completion(issue, gate, report, checked_on="2026-11-10")
    assert decision["failures"] == [
        *_load(DECISION)["failures"],
        "missing published Health 85 evidence (--published-budget)",
    ]
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


def test_qualifying_series_without_published_budget_cannot_complete() -> None:
    report = _qualifying_report()
    decision = reconcile_completion(_issue_for(report), _load(GATE), report)

    assert decision["gate_run_supported"] is True
    assert decision["sustained_series_supported"] is True
    assert decision["observations_match_issue"] is True
    assert decision["action"] == "leave_incomplete"
    assert decision["completion_reconciled"] is False
    assert decision["sustained_performance_criterion"] == "incomplete"
    assert decision["failures"] == ["missing published Health 85 evidence (--published-budget)"]


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
    assert json.loads(output.read_text(encoding="utf-8")) == reconcile_completion(
        _load(ISSUE_VIEW), _load(GATE), _load(BUDGET), checked_on="2026-11-10"
    )


def test_before_after_gate_runs_demonstrate_measured_reduction() -> None:
    before = _load(PRE_GATE)
    after = _load(GATE)
    comparison = compare_before_after_gate_runs(before, after)
    assert comparison["measured_reduction"] is True
    assert comparison["failures"] == []
    assert comparison["before_run_id"] == DEFAULT_PRE_CHANGE_RUN_ID
    assert comparison["after_run_id"] == DEFAULT_POST_CHANGE_RUN_ID
    assert comparison["before_job_seconds"] == 2304.0
    assert comparison["after_job_seconds"] == 349.0
    assert comparison["job_reduction_seconds"] == 1955.0
    assert comparison["before_pytest_seconds"] == 2263.0
    assert comparison["after_pytest_seconds"] == 298.0
    assert comparison["pytest_reduction_seconds"] == 1965.0


def test_compare_before_after_gate_runs_detects_missing_or_regressed_timings() -> None:
    before = _load(PRE_GATE)
    after = deepcopy(_load(GATE))
    after["run_id"] = 999
    after["gh_run_view"]["jobs"] = []
    comparison = compare_before_after_gate_runs(before, after)
    assert comparison["measured_reduction"] is False
    assert any("after run_id is 999" in f for f in comparison["failures"])
    assert any("after run missing embedded job" in f for f in comparison["failures"])


def test_verify_published_ci_budget_alignment_matches_retained_series() -> None:
    retained = _load(BUDGET)
    published = {
        "stranske/Workflows": {
            "p50": 11.133333333333333,
            "p50_series": {
                "2026-11-04": 11.85,
                "2026-11-05": None,
                "2026-11-06": None,
                "2026-11-07": None,
                "2026-11-10": 11.133333333333333,
            },
            "daily_observations": {
                "2026-11-10": {
                    "date": "2026-11-10",
                    "measured_at": "2026-11-10T14:55:15+00:00",
                    "p50_minutes": 11.133333333333333,
                    "run_attempt": 1,
                    "run_id": 42838942059,
                    "source_run_url": "https://github.com/stranske/Workflows/actions/runs/42838942059",
                    "window_start": "2026-11-03T14:55:15+00:00",
                }
            },
        }
    }
    ok, failures = verify_published_ci_budget_alignment(published, retained)
    assert ok is True
    assert failures == []

    mismatched = deepcopy(published)
    mismatched["stranske/Workflows"]["p50_series"]["2026-11-10"] = 9.5
    ok_bad, failures_bad = verify_published_ci_budget_alignment(mismatched, retained)
    assert ok_bad is False
    assert any("date 2026-11-10 p50 mismatch" in f for f in failures_bad)

    mismatched_native = deepcopy(published)
    mismatched_native["stranske/Workflows"]["daily_observations"]["2026-11-10"]["run_id"] = 999
    mismatched_native["stranske/Workflows"]["daily_observations"]["2026-11-10"]["p50_minutes"] = 9.0
    ok_nat, failures_nat = verify_published_ci_budget_alignment(mismatched_native, retained)
    assert ok_nat is False
    assert any("date 2026-11-10 run_id mismatch" in f for f in failures_nat)
    assert any("date 2026-11-10 native p50 mismatch" in f for f in failures_nat)

    missing_day = deepcopy(published)
    missing_day["stranske/Workflows"]["p50_series"]["2026-11-11"] = 9.0
    ok_miss, failures_miss = verify_published_ci_budget_alignment(missing_day, retained)
    assert ok_miss is False
    assert any("published date 2026-11-11 missing" in f for f in failures_miss)

    assert verify_published_ci_budget_alignment({}, retained)[0] is False
    assert verify_published_ci_budget_alignment({"stranske/Workflows": {}}, retained)[0] is False
    assert verify_published_ci_budget_alignment(published, {})[0] is False


def test_compare_before_after_edge_cases() -> None:
    before = deepcopy(_load(PRE_GATE))
    after = deepcopy(_load(GATE))
    before["run_id"] = 111
    before["gh_run_view"] = "invalid"
    res = compare_before_after_gate_runs(before, after)
    assert res["measured_reduction"] is False
    assert any("before run_id is 111" in f for f in res["failures"])
    assert any("before run missing embedded job" in f for f in res["failures"])

    before_non_list = deepcopy(_load(PRE_GATE))
    before_non_list["gh_run_view"]["jobs"] = "invalid"
    assert compare_before_after_gate_runs(before_non_list, after)["measured_reduction"] is False

    # Test non-decreasing job and pytest step durations
    slow_after = deepcopy(_load(GATE))
    for job in slow_after["gh_run_view"]["jobs"]:
        if job["name"] == "python ci / python 3.13":
            job["startedAt"] = "2026-11-10T13:00:00Z"
            job["completedAt"] = "2026-11-10T14:00:00Z"
            for step in job["steps"]:
                if step["name"].startswith("Pytest (unit tests"):
                    step["startedAt"] = "2026-11-10T13:00:00Z"
                    step["completedAt"] = "2026-11-10T14:00:00Z"
    res_slow = compare_before_after_gate_runs(_load(PRE_GATE), slow_after)
    assert res_slow["measured_reduction"] is False
    assert any("job duration did not decrease" in f for f in res_slow["failures"])
    assert any("Pytest step duration did not decrease" in f for f in res_slow["failures"])


def test_gate_run_supported_and_cli_error_branches(tmp_path: Path) -> None:
    from scripts.issue_4619_completion import _flag, gate_run_supported

    assert _flag("other") == "other"
    ok, failures = gate_run_supported(
        {
            "run_id": 123,
            "passed": False,
            "failures": ["custom failure"],
            "jobs": [
                {
                    "name": "python ci / python 3.13",
                    "seconds": True,
                    "status": "in_progress",
                    "conclusion": "failure",
                    "url": "invalid",
                }
            ],
        }
    )
    assert ok is False
    assert any("run_id is 123" in f for f in failures)
    assert any("missing job python ci / python 3.14" in f for f in failures)
    assert any("has no duration" in f for f in failures)
    assert any("is not completed/success" in f for f in failures)
    assert any("has no job URL" in f for f in failures)
    assert "custom failure" in failures

    ok2, failures2 = gate_run_supported(
        {
            "run_id": DEFAULT_POST_CHANGE_RUN_ID,
            "passed": False,
            "jobs": deepcopy(_load(GATE)["jobs"]),
        }
    )
    assert ok2 is False
    assert "gate evidence passed flag is false" in failures2

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("[]\n", encoding="utf-8")
    out = tmp_path / "out.json"
    assert (
        main(
            [
                "--issue-view",
                str(bad_json),
                "--gate-evidence",
                str(GATE),
                "--budget",
                str(BUDGET),
                "--output",
                str(out),
            ]
        )
        == 1
    )
    empty_state = tmp_path / "empty_state.json"
    empty_state.write_text('{"state": ""}\n', encoding="utf-8")
    assert (
        main(
            [
                "--issue-view",
                str(empty_state),
                "--gate-evidence",
                str(GATE),
                "--budget",
                str(BUDGET),
                "--output",
                str(out),
            ]
        )
        == 1
    )


def test_evaluate_native_daily_observations_validates_seven_day_series() -> None:
    now = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    observations = {}
    for offset in range(7):
        dt = now - timedelta(days=6 - offset)
        day = dt.date().isoformat()
        observations[day] = {
            "date": day,
            "p50_minutes": 9.2,
            "run_id": 50000 + offset,
            "run_attempt": 1,
            "measured_at": dt.isoformat(),
            "window_start": (dt - timedelta(days=7)).isoformat(),
            "source_run_url": f"https://github.com/stranske/Workflows/actions/runs/{50000 + offset}",
        }
    report = {"stranske/Workflows": {"daily_observations": observations}}
    evaluated = evaluate_native_daily_observations(report, now)
    assert evaluated["qualifying_seven_day_series"] is True
    assert evaluated["failures"] == []
    assert len(evaluated["observations"]) == 7
    assert evaluated["observations"][0]["run_attempt"] == 1

    # Missing dates fail closed
    partial = deepcopy(report)
    partial["stranske/Workflows"]["daily_observations"].pop("2026-11-08")
    partial_eval = evaluate_native_daily_observations(partial, now)
    assert partial_eval["qualifying_seven_day_series"] is False
    assert any("missing native dates: 2026-11-08" in f for f in partial_eval["failures"])

    # Empty report
    empty_eval = evaluate_native_daily_observations(
        {"stranske/Workflows": {"daily_observations": "bad"}}, now
    )
    assert empty_eval["qualifying_seven_day_series"] is False
    assert "no source-bound native observations retained" in empty_eval["failures"]

    # Invalid p50 value
    bad_p50 = deepcopy(report)
    bad_p50["stranske/Workflows"]["daily_observations"]["2026-11-10"]["p50_minutes"] = -1.0
    with pytest.raises(ValueError, match="invalid native p50"):
        evaluate_native_daily_observations(bad_p50, now)

    # Invalid timestamps
    bad_ts = deepcopy(report)
    bad_ts["stranske/Workflows"]["daily_observations"]["2026-11-10"]["measured_at"] = None
    with pytest.raises(ValueError, match="invalid native observation timestamps"):
        evaluate_native_daily_observations(bad_ts, now)

    # Invalid identity
    bad_id = deepcopy(report)
    bad_id["stranske/Workflows"]["daily_observations"]["2026-11-10"]["run_id"] = 0
    with pytest.raises(ValueError, match="invalid native observation identity"):
        evaluate_native_daily_observations(bad_id, now)


def test_reconcile_completion_and_main_with_published_budget(tmp_path: Path) -> None:
    report = _qualifying_report()
    native = {}
    for offset, row in enumerate(report["observations"]):
        measured_at = datetime.fromisoformat(row["date"]).replace(tzinfo=UTC)
        row.update(run_id=6000 + offset, p50_minutes=9.0)
        native[row["date"]] = {
            **row,
            "measured_at": measured_at.isoformat(),
            "window_start": (measured_at - timedelta(days=7)).isoformat(),
        }
    report["p50_series_minutes"] = {row["date"]: 9.0 for row in report["observations"]}
    published_ok = {
        "stranske/Workflows": {
            "p50_series": report["p50_series_minutes"],
            "daily_observations": native,
        }
    }
    decision = reconcile_completion(
        _issue_for(report),
        _load(GATE),
        report,
        published_budget=published_ok,
    )
    assert decision["published_budget_aligned"] is True
    assert decision["native_observations_match"] is True
    assert decision["native_series_qualifying"] is True
    assert decision["completion_reconciled"] is True
    assert decision["action"] == "mark_complete"
    assert decision["both_gates_supported"] is True
    assert decision["sustained_performance_criterion"] == "complete"
    assert decision["issue_mutation"] == "none"
    assert decision["failures"] == []

    published_without_native = {"stranske/Workflows": {"p50_series": report["p50_series_minutes"]}}
    decision_bad = reconcile_completion(
        _issue_for(report),
        _load(GATE),
        report,
        published_budget=published_without_native,
    )
    assert decision_bad["published_budget_aligned"] is True
    assert decision_bad["native_series_qualifying"] is False
    assert decision_bad["completion_reconciled"] is False
    assert decision_bad["sustained_performance_criterion"] == "incomplete"

    pub_file = tmp_path / "published.json"
    pub_file.write_text(json.dumps(published_ok), encoding="utf-8")
    out_file = tmp_path / "out.json"
    assert (
        main(
            [
                "--issue-view",
                str(ISSUE_VIEW),
                "--gate-evidence",
                str(GATE),
                "--budget",
                str(BUDGET),
                "--published-budget",
                str(pub_file),
                "--output",
                str(out_file),
            ]
        )
        == 0
    )

    bad_pub_file = tmp_path / "bad_pub.json"
    bad_pub_file.write_text("[]\n", encoding="utf-8")
    assert (
        main(
            [
                "--issue-view",
                str(ISSUE_VIEW),
                "--gate-evidence",
                str(GATE),
                "--budget",
                str(BUDGET),
                "--published-budget",
                str(bad_pub_file),
                "--output",
                str(out_file),
            ]
        )
        == 1
    )


def test_verify_published_ci_budget_alignment_and_gate_run_branch_coverage() -> None:
    retained = _load(BUDGET)
    published = {
        "stranske/Workflows": {
            "p50": 11.133333333333333,
            "p50_series": {
                "2026-11-04": 11.85,
                "2026-11-05": None,
                "2026-11-06": None,
                "2026-11-07": None,
                "2026-11-10": 11.133333333333333,
            },
            "daily_observations": "not-a-mapping",
        }
    }
    ok, failures = verify_published_ci_budget_alignment(published, retained)
    assert ok is True
    assert failures == []

    published_with_skipped_days = deepcopy(published)
    published_with_skipped_days["stranske/Workflows"]["daily_observations"] = {
        "2026-11-10": None,
        "2026-11-99": {"run_id": 1, "p50_minutes": 1.0},
    }
    ok2, failures2 = verify_published_ci_budget_alignment(published_with_skipped_days, retained)
    assert ok2 is True
    assert failures2 == []

    bad_jobs_evidence = {
        "run_id": DEFAULT_POST_CHANGE_RUN_ID,
        "jobs": None,
        "passed": False,
        "failures": ["missing job python ci / python 3.13", "extra failure"],
    }
    g_ok, g_fails = gate_run_supported(bad_jobs_evidence)
    assert g_ok is False
    assert "missing job python ci / python 3.13" in g_fails
    assert "extra failure" in g_fails
    assert g_fails.count("missing job python ci / python 3.13") == 1

    non_mapping_job_evidence = {
        "run_id": DEFAULT_POST_CHANGE_RUN_ID,
        "jobs": ["not-a-dict", {"no_name": 1}],
        "passed": False,
        "failures": [],
    }
    g2_ok, g2_fails = gate_run_supported(non_mapping_job_evidence)
    assert g2_ok is False
    assert "missing job python ci / python 3.13" in g2_fails

    passed_flag_false_evidence = deepcopy(_load(GATE))
    passed_flag_false_evidence["passed"] = False
    g3_ok, g3_fails = gate_run_supported(passed_flag_false_evidence)
    assert g3_ok is False
    assert "gate evidence passed flag is false" in g3_fails


def test_gate_run_supported_rejects_invalid_durations() -> None:
    """gate_run_supported must reject non-finite and negative durations."""
    # Test with negative duration
    neg_job = {
        "run_id": DEFAULT_POST_CHANGE_RUN_ID,
        "passed": True,
        "jobs": [
            {
                "name": "python ci / python 3.13",
                "seconds": -1.0,
                "status": "completed",
                "conclusion": "success",
                "url": "https://github.com/stranske/Workflows/actions/runs/123",
            },
            {
                "name": "python ci / python 3.14",
                "seconds": 300.0,
                "status": "completed",
                "conclusion": "success",
                "url": "https://github.com/stranske/Workflows/actions/runs/124",
            },
        ],
        "failures": [],
    }
    ok, failures = gate_run_supported(neg_job)
    assert ok is False
    assert any("invalid duration" in f for f in failures)

    # Test with infinity
    inf_job = deepcopy(neg_job)
    inf_job["jobs"][0]["seconds"] = float("inf")
    ok_inf, failures_inf = gate_run_supported(inf_job)
    assert ok_inf is False
    assert any("invalid duration" in f for f in failures_inf)

    # Test with NaN
    nan_job = deepcopy(neg_job)
    nan_job["jobs"][0]["seconds"] = float("nan")
    ok_nan, failures_nan = gate_run_supported(nan_job)
    assert ok_nan is False
    assert any("invalid duration" in f for f in failures_nan)


def test_load_object_catches_oserror_and_valueerror(tmp_path: Path) -> None:
    """_load_object must catch OSError and ValueError."""
    from scripts.issue_4619_completion import _load_object

    # Test with non-existent file (OSError)
    nonexistent = tmp_path / "nonexistent.json"
    result = _load_object(nonexistent)
    assert result is None

    # Test with invalid JSON (ValueError)
    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("not valid json", encoding="utf-8")
    result_invalid = _load_object(invalid_json)
    assert result_invalid is None

    # Test with valid JSON but not an object
    array_json = tmp_path / "array.json"
    array_json.write_text("[]", encoding="utf-8")
    result_array = _load_object(array_json)
    assert result_array is None


def test_evaluate_native_daily_observations_wired_into_reconciliation() -> None:
    """When published_budget is supplied, evaluate_native_daily_observations is used."""
    now = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

    # Create valid native observations
    observations = {}
    for offset in range(7):
        dt = now - timedelta(days=6 - offset)
        day = dt.date().isoformat()
        observations[day] = {
            "date": day,
            "p50_minutes": 9.2,
            "run_id": 50000 + offset,
            "run_attempt": 1,
            "measured_at": dt.isoformat(),
            "window_start": (dt - timedelta(days=7)).isoformat(),
            "source_run_url": f"https://github.com/stranske/Workflows/actions/runs/{50000 + offset}",
        }

    # Create matching report observations
    report_obs = []
    for offset in range(7):
        dt = now - timedelta(days=6 - offset)
        day = dt.date().isoformat()
        report_obs.append(
            {
                "date": day,
                "p50_minutes": 9.2,
                "run_id": 50000 + offset,
                "p50_seconds": 552.0,
                "within_600_seconds": True,
                "status": "measured",
                "run_conclusion": "success",
                "source_run_url": f"https://github.com/stranske/Workflows/actions/runs/{50000 + offset}",
                "note": None,
            }
        )

    report = {
        "repo": "stranske/Workflows",
        "target_minutes": 10.0,
        "max_seconds": 600.0,
        "consecutive_calendar_dates": True,
        "qualifying_seven_day_series": True,
        "failures": [],
        "p50_series_minutes": {obs["date"]: 9.2 for obs in report_obs},
        "observations": report_obs,
    }

    published_budget = {
        "stranske/Workflows": {
            "daily_observations": observations,
        }
    }

    decision = reconcile_completion(
        _issue_for(report),
        _load(GATE),
        report,
        published_budget=published_budget,
    )

    # Should have native observation checks in decision
    assert "native_observations_match" in decision
    assert decision["native_observations_match"] is True
    assert "native_series_qualifying" in decision


def test_native_observations_match_rejects_incomplete_evidence() -> None:
    """verify_native_daily_observations_match rejects partial/incomplete native evidence."""
    # Create report with observations
    report_obs = [
        {"date": "2026-11-04", "p50_minutes": 9.2, "run_id": 50000},
        {"date": "2026-11-05", "p50_minutes": 9.2, "run_id": 50001},
    ]
    report = {
        "observations": report_obs,
        "p50_series_minutes": {"2026-11-04": 9.2, "2026-11-05": 9.2},
    }

    # Published budget with only one observation (missing 2026-11-05)
    published_budget = {
        "stranske/Workflows": {
            "daily_observations": {
                "2026-11-04": {
                    "date": "2026-11-04",
                    "p50_minutes": 9.2,
                    "run_id": 50000,
                },
            },
        },
    }

    ok, failures = verify_native_daily_observations_match(published_budget, report)
    assert ok is False
    assert any("missing date" in f for f in failures)

    # Published budget with mismatched run_id
    published_budget_bad = {
        "stranske/Workflows": {
            "daily_observations": {
                "2026-11-04": {
                    "date": "2026-11-04",
                    "p50_minutes": 9.2,
                    "run_id": 99999,  # Wrong run_id
                },
                "2026-11-05": {
                    "date": "2026-11-05",
                    "p50_minutes": 9.2,
                    "run_id": 50001,
                },
            },
        },
    }
    ok_bad, failures_bad = verify_native_daily_observations_match(published_budget_bad, report)
    assert ok_bad is False
    assert any("run_id mismatch" in f for f in failures_bad)

    # Published budget with mismatched p50_minutes
    published_budget_p50 = {
        "stranske/Workflows": {
            "daily_observations": {
                "2026-11-04": {
                    "date": "2026-11-04",
                    "p50_minutes": 10.0,  # Wrong p50
                    "run_id": 50000,
                },
                "2026-11-05": {
                    "date": "2026-11-05",
                    "p50_minutes": 9.2,
                    "run_id": 50001,
                },
            },
        },
    }
    ok_p50, failures_p50 = verify_native_daily_observations_match(published_budget_p50, report)
    assert ok_p50 is False
    assert any("p50_minutes mismatch" in f for f in failures_p50)


def test_reconciliation_fails_closed_on_missing_native_dates() -> None:
    """Reconciliation fails closed when native observations are missing or invalid."""
    report = _qualifying_report()

    # Published budget missing daily_observations entirely
    published_incomplete = {
        "stranske/Workflows": {
            "p50_series": {row["date"]: 9.0 for row in report["observations"]},
        }
    }

    decision = reconcile_completion(
        _issue_for(report),
        _load(GATE),
        report,
        published_budget=published_incomplete,
    )

    assert decision["completion_reconciled"] is False
    assert decision["action"] == "leave_incomplete"
    assert any("daily_observations" in f or "native" in f.lower() for f in decision["failures"])
