"""Unit tests for Gate python job timing policy (issue #4260)."""

from __future__ import annotations

import json
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
            "started_at": "2026-10-26T10:00:00Z",
            "completed_at": "2026-10-26T10:07:00Z",
        },
        {
            "name": "python ci / python 3.14",
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
            {"id": 1, "conclusion": "success"},
            {"id": 2, "conclusion": "failure"},
            {"id": 3, "conclusion": "success"},
            {"id": 4, "conclusion": "success"},
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


def test_collect_policy_sample_and_main_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = {
        "workflow_runs": [
            {"id": 11, "conclusion": "success"},
            {"id": 12, "conclusion": "success"},
        ]
    }
    jobs_by_run = {
        11: {
            "jobs": [
                {
                    "name": "python ci / python 3.13",
                    "started_at": "2026-10-26T10:00:00Z",
                    "completed_at": "2026-10-26T10:05:00Z",
                },
                {
                    "name": "python ci / python 3.14",
                    "started_at": "2026-10-26T10:00:00Z",
                    "completed_at": "2026-10-26T10:08:00Z",
                },
            ]
        },
        12: {
            "jobs": [
                {
                    "name": "python ci / python 3.13",
                    "started_at": "2026-10-26T11:00:00Z",
                    "completed_at": "2026-10-26T11:06:00Z",
                },
                {
                    "name": "python ci / python 3.14",
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
    passed, failures = timings.evaluate_policy(sample, max_seconds=600)
    assert passed is True
    assert failures == []

    report_path = tmp_path / "report.json"
    assert (
        timings.main(
            [
                "--limit",
                "2",
                "--max-seconds",
                "600",
                "--json-out",
                str(report_path),
            ]
        )
        == 0
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["policy"]["run_count"] == 2


def test_main_fails_when_job_over_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    runs = {"workflow_runs": [{"id": 21, "conclusion": "success"}]}
    jobs = {
        "jobs": [
            {
                "name": "python ci / python 3.13",
                "started_at": "2026-10-26T10:00:00Z",
                "completed_at": "2026-10-26T10:05:00Z",
            },
            {
                "name": "python ci / python 3.14",
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
                "started_at": "2026-10-26T10:37:58Z",
                "completed_at": "2026-10-26T10:49:11Z",
            },
            {
                "name": "python ci / python 3.14",
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
                "python ci / python 3.13": 673.0,
                "python ci / python 3.14": 560.0,
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


def test_collect_run_ids_sample_requires_ids() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        timings.collect_run_ids_sample(repo="stranske/Workflows", run_ids=[], token="tok")
