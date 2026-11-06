"""Delivery evidence for issue #4284 Gate run 40551187519."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.gate_run_view_evidence import (
    NAMED_JOBS,
    evidence_json,
    recalculated_matches,
    retain_gate_run_view,
)

EVIDENCE_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "evidence"
    / "issue-4284"
    / "gate-run-40551187519.json"
)

PYTHON_313_URL = "https://github.com/stranske/Workflows/actions/runs/40551187519/job/122355504848"
PYTHON_314_URL = "https://github.com/stranske/Workflows/actions/runs/40551187519/job/122355504921"


def _job(
    name: str,
    *,
    started: str = "2026-10-27T17:31:00Z",
    completed: str = "2026-10-27T17:38:59Z",
    conclusion: str = "success",
    url: str | None = PYTHON_313_URL,
    database_id: int = 122355504848,
) -> dict:
    job = {
        "name": name,
        "databaseId": database_id,
        "status": "completed",
        "conclusion": conclusion,
        "startedAt": started,
        "completedAt": completed,
        "steps": [
            {
                "name": "Pytest (unit tests with coverage)",
                "status": "completed",
                "conclusion": "success",
                "startedAt": started,
                "completedAt": completed,
                "number": 10,
            }
        ],
    }
    if url is not None:
        job["url"] = url
    return job


def _payload(*jobs: dict, status: str = "completed", conclusion: str = "success") -> dict:
    return {"status": status, "conclusion": conclusion, "jobs": list(jobs)}


def test_job_duration_seconds_reads_gh_run_view_camel_case() -> None:
    from scripts.check_gate_python_job_timings import job_duration_seconds

    assert job_duration_seconds(_job("python ci / python 3.13")) == 479.0


def test_retain_gate_run_view_records_urls_and_durations() -> None:
    evidence = retain_gate_run_view(
        _payload(
            _job("python ci / python 3.13"),
            _job(
                "python ci / python 3.14",
                completed="2026-10-27T17:40:40Z",
                url=PYTHON_314_URL,
                database_id=122355504921,
            ),
            _job(
                "summary", completed="2026-10-27T17:41:00Z", url="https://example.invalid/summary"
            ),
        )
    )
    assert evidence["passed"] is True
    assert evidence["failures"] == []
    assert evidence["gh_run_view"]["conclusion"] == "success"
    assert [job["name"] for job in evidence["gh_run_view"]["jobs"]] == list(NAMED_JOBS)
    assert evidence["jobs"] == [
        {
            "name": "python ci / python 3.13",
            "database_id": 122355504848,
            "status": "completed",
            "conclusion": "success",
            "started_at": "2026-10-27T17:31:00Z",
            "completed_at": "2026-10-27T17:38:59Z",
            "seconds": 479.0,
            "url": PYTHON_313_URL,
            "within_limit": True,
        },
        {
            "name": "python ci / python 3.14",
            "database_id": 122355504921,
            "status": "completed",
            "conclusion": "success",
            "started_at": "2026-10-27T17:31:00Z",
            "completed_at": "2026-10-27T17:40:40Z",
            "seconds": 580.0,
            "url": PYTHON_314_URL,
            "within_limit": True,
        },
    ]
    assert recalculated_matches(evidence)


def test_retain_gate_run_view_rejects_over_limit_and_failed_run() -> None:
    slow = retain_gate_run_view(
        _payload(
            _job("python ci / python 3.13", completed="2026-10-27T17:41:01Z"),
            _job(
                "python ci / python 3.14",
                completed="2026-10-27T17:40:40Z",
                url=PYTHON_314_URL,
                database_id=122355504921,
            ),
        )
    )
    assert slow["passed"] is False
    assert slow["jobs"][0]["seconds"] == 601.0
    assert slow["jobs"][0]["within_limit"] is False
    assert any("python ci / python 3.13 took 601s" in failure for failure in slow["failures"])

    failed = retain_gate_run_view(
        _payload(
            _job("python ci / python 3.13", conclusion="failure"),
            _job("python ci / python 3.14", url=PYTHON_314_URL, database_id=122355504921),
            conclusion="failure",
        )
    )
    assert failed["passed"] is False
    assert any("run conclusion" in failure for failure in failed["failures"])
    assert any("python ci / python 3.13" in failure for failure in failed["failures"])


def test_retain_gate_run_view_reports_a_missing_job_and_url() -> None:
    evidence = retain_gate_run_view(_payload(_job("python ci / python 3.13", url=None)))
    assert evidence["passed"] is False
    assert "missing job 'python ci / python 3.14'" in evidence["failures"]
    assert "python ci / python 3.13 has no job URL" in evidence["failures"]


def test_committed_run_40551187519_evidence_meets_the_600_second_gate() -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert evidence["schema"] == "issue-4284-gate-run-view/v1"
    assert evidence["issue"] == 4284
    assert evidence["run_id"] == 40551187519
    assert evidence["passed"] is True
    assert evidence["failures"] == []
    assert evidence["gh_run_view"]["status"] == "completed"
    assert evidence["gh_run_view"]["conclusion"] == "success"
    by_name = {job["name"]: job for job in evidence["jobs"]}
    assert by_name["python ci / python 3.13"]["seconds"] == 479.0
    assert by_name["python ci / python 3.13"]["url"] == PYTHON_313_URL
    assert by_name["python ci / python 3.14"]["seconds"] == 580.0
    assert by_name["python ci / python 3.14"]["url"] == PYTHON_314_URL
    assert all(job["seconds"] <= 600 for job in evidence["jobs"])
    assert recalculated_matches(evidence)
    assert evidence_json(evidence) == EVIDENCE_PATH.read_text(encoding="utf-8")


def test_recalculated_matches_rejects_a_tampered_duration() -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    evidence["jobs"][0]["seconds"] = 1.0
    assert recalculated_matches(evidence) is False


def test_max_seconds_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_seconds"):
        retain_gate_run_view(_payload(), max_seconds=0)
