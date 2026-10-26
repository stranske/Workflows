"""Unit tests for Gate python job timing policy (issue #4260)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from scripts import check_gate_python_job_timings as timings


def test_job_duration_seconds_parses_github_timestamps() -> None:
    job = {
        "started_at": "2026-10-26T10:00:00Z",
        "completed_at": "2026-10-26T10:08:00Z",
    }
    assert timings.job_duration_seconds(job) == 480.0


def test_job_duration_seconds_rejects_missing_or_inverted() -> None:
    assert timings.job_duration_seconds({"started_at": "2026-10-26T10:00:00Z"}) is None
    assert (
        timings.job_duration_seconds(
            {
                "started_at": "2026-10-26T10:08:00Z",
                "completed_at": "2026-10-26T10:00:00Z",
            }
        )
        is None
    )


def test_extract_python_job_durations_keeps_target_jobs_only() -> None:
    jobs = [
        {
            "name": "python ci / python 3.13",
            "status": "completed",
            "conclusion": "success",
            "started_at": "2026-10-26T10:00:00Z",
            "completed_at": "2026-10-26T10:07:00Z",
            "steps": [
                {
                    "name": "Pytest (unit tests with coverage)",
                    "started_at": "2026-10-26T10:00:30Z",
                    "completed_at": "2026-10-26T10:06:30Z",
                }
            ],
        },
        {
            "name": "python ci / python 3.14",
            "status": "completed",
            "conclusion": "success",
            "started_at": "2026-10-26T10:00:00Z",
            "completed_at": "2026-10-26T10:09:30Z",
        },
        {
            "name": "summary",
            "started_at": "2026-10-26T10:00:00Z",
            "completed_at": "2026-10-26T10:20:00Z",
        },
    ]
    assert timings.extract_python_job_durations(jobs) == {
        "python ci / python 3.13": 420.0,
        "python ci / python 3.14": 570.0,
    }
    detailed = timings.extract_python_job_timings(jobs)
    assert detailed["python ci / python 3.13"] == timings.JobTiming(420.0, 360.0)
    assert detailed["python ci / python 3.14"] == timings.JobTiming(570.0, None)


@pytest.mark.parametrize(
    "status,conclusion",
    [
        ("completed", "failure"),
        ("completed", "cancelled"),
        ("completed", "skipped"),
        ("completed", "timed_out"),
        ("completed", "neutral"),
        ("completed", None),
        ("in_progress", "success"),
        (None, "success"),
    ],
)
def test_unsuccessful_target_job_cannot_pass_timing_policy(status, conclusion) -> None:
    jobs = [
        {
            "name": name,
            "status": "completed",
            "conclusion": "success",
            "started_at": "2026-10-26T10:00:00Z",
            "completed_at": "2026-10-26T10:05:00Z",
        }
        for name in timings.TARGET_JOB_NAMES
    ]
    jobs[0].update(status=status, conclusion=conclusion)

    durations = timings.extract_python_job_durations(jobs)
    passed, failures = timings.evaluate_policy([(101, durations)])

    assert passed is False
    assert timings.TARGET_JOB_NAMES[0] not in durations
    assert failures == ["run 101: missing job 'python ci / python 3.13'"]


def test_parse_created_after_accepts_date_and_timestamp() -> None:
    assert timings.parse_created_after("2026-11-15") == datetime(2026, 11, 15, tzinfo=UTC)
    assert timings.parse_created_after("2026-11-15T12:30:00Z") == datetime(
        2026, 11, 15, 12, 30, tzinfo=UTC
    )
    with pytest.raises(ValueError, match="created-after"):
        timings.parse_created_after("not-a-date")


def test_evaluate_run_timings_flags_over_limit_and_missing() -> None:
    failures = timings.evaluate_run_timings(
        101,
        {"python ci / python 3.14": 590.0},
        max_seconds=600,
    )
    assert failures == [
        "run 101: missing job 'python ci / python 3.13'",
    ]

    failures = timings.evaluate_run_timings(
        102,
        {
            "python ci / python 3.13": 601.0,
            "python ci / python 3.14": 500.0,
        },
        max_seconds=600,
    )
    assert failures == ["run 102: python ci / python 3.13 took 601s (limit 600s)"]


def test_evaluate_policy_requires_all_runs_within_limit() -> None:
    sample = [
        (
            1,
            {
                "python ci / python 3.13": 400.0,
                "python ci / python 3.14": 500.0,
            },
        ),
        (
            2,
            {
                "python ci / python 3.13": 400.0,
                "python ci / python 3.14": 700.0,
            },
        ),
    ]
    passed, failures = timings.evaluate_policy(sample, max_seconds=600)
    assert passed is False
    assert failures == ["run 2: python ci / python 3.14 took 700s (limit 600s)"]

    ok_sample = [
        (
            1,
            {
                "python ci / python 3.13": 400.0,
                "python ci / python 3.14": 500.0,
            },
        ),
        (
            2,
            {
                "python ci / python 3.13": 590.0,
                "python ci / python 3.14": 600.0,
            },
        ),
    ]
    passed, failures = timings.evaluate_policy(ok_sample, max_seconds=600)
    assert passed is True
    assert failures == []


def test_list_successful_pr_runs_filters_and_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "workflow_runs": [
            {"id": 1, "conclusion": "success", "created_at": "2026-11-16T01:00:00Z"},
            {"id": 2, "conclusion": "failure", "created_at": "2026-11-16T02:00:00Z"},
            {"id": 3, "conclusion": "success", "created_at": "2026-11-14T01:00:00Z"},
            {"id": 4, "conclusion": "success", "created_at": "2026-11-15T00:00:00Z"},
        ]
    }

    def fake_get(path: str, token: str) -> dict:
        assert "event=pull_request" in path
        assert "status=success" in path
        assert token == "tok"
        return payload

    selected = timings.list_successful_pr_runs(
        repo="stranske/Workflows",
        workflow="pr-00-gate.yml",
        limit=2,
        token="tok",
        get_json=fake_get,
    )
    assert [run["id"] for run in selected] == [1, 3]

    after = timings.list_successful_pr_runs(
        repo="stranske/Workflows",
        workflow="pr-00-gate.yml",
        limit=5,
        token="tok",
        get_json=fake_get,
        created_after=timings.parse_created_after("2026-11-15"),
    )
    assert [run["id"] for run in after] == [1, 4]


def test_collect_policy_sample_and_main_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = {
        "workflow_runs": [
            {"id": 11, "conclusion": "success", "created_at": "2026-11-15T10:00:00Z"},
            {"id": 12, "conclusion": "success", "created_at": "2026-11-15T11:00:00Z"},
        ]
    }
    jobs_by_run = {
        11: {
            "jobs": [
                {
                    "name": "python ci / python 3.13",
                    "status": "completed",
                    "conclusion": "success",
                    "started_at": "2026-10-26T10:00:00Z",
                    "completed_at": "2026-10-26T10:05:00Z",
                    "steps": [
                        {
                            "name": "Pytest (unit tests with coverage)",
                            "started_at": "2026-10-26T10:00:20Z",
                            "completed_at": "2026-10-26T10:04:40Z",
                        }
                    ],
                },
                {
                    "name": "python ci / python 3.14",
                    "status": "completed",
                    "conclusion": "success",
                    "started_at": "2026-10-26T10:00:00Z",
                    "completed_at": "2026-10-26T10:08:00Z",
                },
            ]
        },
        12: {
            "jobs": [
                {
                    "name": "python ci / python 3.13",
                    "status": "completed",
                    "conclusion": "success",
                    "started_at": "2026-10-26T11:00:00Z",
                    "completed_at": "2026-10-26T11:06:00Z",
                },
                {
                    "name": "python ci / python 3.14",
                    "status": "completed",
                    "conclusion": "success",
                    "started_at": "2026-10-26T11:00:00Z",
                    "completed_at": "2026-10-26T11:09:00Z",
                },
            ]
        },
    }

    def fake_get(path: str, token: str) -> dict:
        if "/runs?" in path:
            return runs
        for run_id, payload in jobs_by_run.items():
            if f"/runs/{run_id}/jobs" in path:
                return payload
        raise AssertionError(path)

    monkeypatch.setattr(timings, "_github_token", lambda: "tok")
    monkeypatch.setattr(timings, "_gh_api", fake_get)

    sample = timings.collect_policy_sample(limit=2, get_json=fake_get, token="tok")
    assert len(sample) == 2
    passed, failures = timings.evaluate_policy(
        [(run_id, timings.durations_from_timings(job_timings)) for run_id, job_timings in sample],
        max_seconds=600,
    )
    assert passed is True
    assert failures == []
    assert sample[0][1]["python ci / python 3.13"].pytest_step_seconds == 260.0

    report_path = tmp_path / "report.json"
    assert (
        timings.main(
            [
                "--limit",
                "2",
                "--max-seconds",
                "600",
                "--created-after",
                "2026-11-15",
                "--json-out",
                str(report_path),
            ]
        )
        == 0
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["policy"]["run_count"] == 2
    assert report["policy"]["created_after"] == "2026-11-15"
    assert report["runs"][0]["jobs"]["python ci / python 3.13"]["pytest_step_seconds"] == 260.0


def test_main_fails_when_job_over_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    runs = {"workflow_runs": [{"id": 21, "conclusion": "success"}]}
    jobs = {
        "jobs": [
            {
                "name": "python ci / python 3.13",
                "status": "completed",
                "conclusion": "success",
                "started_at": "2026-10-26T10:00:00Z",
                "completed_at": "2026-10-26T10:05:00Z",
            },
            {
                "name": "python ci / python 3.14",
                "status": "completed",
                "conclusion": "success",
                "started_at": "2026-10-26T10:00:00Z",
                "completed_at": "2026-10-26T10:12:00Z",
            },
        ]
    }

    def fake_get(path: str, token: str) -> dict:
        if "/runs?" in path:
            return runs
        return jobs

    monkeypatch.setattr(timings, "_github_token", lambda: "tok")
    monkeypatch.setattr(timings, "_gh_api", fake_get)
    assert timings.main(["--limit", "1", "--max-seconds", "600"]) == 1


def test_collect_run_ids_sample_and_main_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--run-id evaluates an explicit Gate run regardless of overall conclusion."""
    jobs = {
        "jobs": [
            {
                "name": "python ci / python 3.13",
                "status": "completed",
                "conclusion": "success",
                "started_at": "2026-10-26T10:37:58Z",
                "completed_at": "2026-10-26T10:49:11Z",
                "steps": [
                    {
                        "name": "Pytest (unit tests with coverage)",
                        "started_at": "2026-10-26T10:38:24Z",
                        "completed_at": "2026-10-26T10:48:54Z",
                    }
                ],
            },
            {
                "name": "python ci / python 3.14",
                "status": "completed",
                "conclusion": "success",
                "started_at": "2026-10-26T10:37:58Z",
                "completed_at": "2026-10-26T10:47:18Z",
            },
        ]
    }

    def fake_get(path: str, token: str) -> dict:
        assert "/runs/40308833794/jobs" in path
        assert "/runs?" not in path
        return jobs

    monkeypatch.setattr(timings, "_github_token", lambda: "tok")
    monkeypatch.setattr(timings, "_gh_api", fake_get)

    sample = timings.collect_run_ids_sample(
        repo="stranske/Workflows",
        run_ids=[40308833794],
        token="tok",
        get_json=fake_get,
    )
    assert sample == [
        (
            40308833794,
            {
                "python ci / python 3.13": timings.JobTiming(673.0, 630.0),
                "python ci / python 3.14": timings.JobTiming(560.0, None),
            },
        )
    ]

    report_path = tmp_path / "pr-head.json"
    assert (
        timings.main(
            [
                "--run-id",
                "40308833794",
                "--max-seconds",
                "600",
                "--json-out",
                str(report_path),
            ]
        )
        == 1
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["passed"] is False
    assert report["policy"]["sample_mode"] == "explicit_run_ids"
    assert report["failures"] == ["run 40308833794: python ci / python 3.13 took 673s (limit 600s)"]
    assert report["runs"][0]["jobs"]["python ci / python 3.13"]["pytest_step_seconds"] == 630.0


def test_collect_run_ids_sample_requires_ids() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        timings.collect_run_ids_sample(repo="stranske/Workflows", run_ids=[], token="tok")


def test_evaluate_policy_rejects_empty_sample() -> None:
    passed, failures = timings.evaluate_policy([])
    assert passed is False
    assert failures == ["Only found 0 runs (needed 1)"]


@pytest.mark.parametrize("required_run_count", [0, -1])
def test_evaluate_policy_rejects_invalid_required_run_count(required_run_count: int) -> None:
    with pytest.raises(ValueError, match="required_run_count must be >= 1"):
        timings.evaluate_policy([], required_run_count=required_run_count)


@pytest.mark.parametrize("run_count", [0, 1, 4, 5])
def test_main_records_incomplete_successful_pr_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run_count: int
) -> None:
    """An incomplete dated window must replace stale passing JSON with failure evidence."""
    sample = [
        (run_id, {name: timings.JobTiming(480.0) for name in timings.TARGET_JOB_NAMES})
        for run_id in range(run_count)
    ]

    def collect_sample(**kwargs):
        assert kwargs["limit"] == 5
        assert kwargs["created_after"] == datetime(2026, 11, 15, tzinfo=UTC)
        return sample

    monkeypatch.setattr(timings, "collect_policy_sample", collect_sample)
    report_path = tmp_path / "dated-window.json"
    report_path.write_text('{"passed": true}\n', encoding="utf-8")
    result = timings.main(["--created-after", "2026-11-15", "--json-out", str(report_path)])

    complete = run_count == 5
    assert result == (0 if complete else 1)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["passed"] is complete
    assert report["policy"]["required_run_count"] == 5
    assert report["policy"]["run_count"] == run_count
    assert report["policy"]["created_after"] == "2026-11-15"
    assert len(report["runs"]) == run_count
    assert report["failures"] == ([] if complete else [f"Only found {run_count} runs (needed 5)"])
