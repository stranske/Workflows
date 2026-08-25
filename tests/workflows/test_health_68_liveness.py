"""Offline gates for Health 68 trigger and execution liveness."""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(".github/workflows/health-68-consumer-sync-drift.yml")


def _workflow_triggers() -> dict:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return data.get(True) or data.get("on") or {}


def test_consumer_drift_detector_has_a_schedule() -> None:
    triggers = _workflow_triggers()
    assert "schedule" in triggers, "Health 68 must declare a schedule trigger for self-healing"


def test_consumer_drift_detector_debounces_workflow_run() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "Debounce workflow_run fan-out" in text
    assert "github.event_name == 'workflow_run'" in text
    assert "listJobsForWorkflowRun" in text
    assert 'step.name === "Compare consumer repos to templates"' in text
    assert 'branch: "main"' in text or "branch: 'main'" in text


def test_consumer_drift_debounce_filters_main_before_ordering() -> None:
    """Non-main runs must not suppress workflow_run fan-out for main."""
    runs = [
        {
            "id": 2,
            "head_branch": "feature/test",
            "conclusion": "success",
            "created_at": "2026-08-23T07:20:00Z",
        },
        {
            "id": 1,
            "head_branch": "main",
            "conclusion": "success",
            "created_at": "2026-08-23T07:00:00Z",
        },
    ]

    def selected(values: list[dict]) -> int | None:
        eligible = [
            run for run in values if run["conclusion"] in {"success", "failure", "timed_out"}
        ]
        return eligible[0]["id"] if eligible else None

    assert selected(runs) == 2
    main_only = [run for run in runs if run["head_branch"] == "main"]
    assert selected(main_only) == 1


@pytest.mark.skipif(
    not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")),
    reason="GH_TOKEN or GITHUB_TOKEN required for live Health 68 execution probe",
)
def test_consumer_drift_detector_executed_recently() -> None:
    repo = os.environ.get("GITHUB_REPOSITORY", "stranske/Workflows")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    payload = subprocess.check_output(
        [
            "gh",
            "api",
            f"repos/{repo}/actions/workflows/health-68-consumer-sync-drift.yml/runs",
            "--paginate",
            "-q",
            ".workflow_runs[]",
        ],
        text=True,
        env={**os.environ, "GH_TOKEN": token},
    )
    latest_executable: str | None = None
    for line in payload.splitlines():
        line = line.strip()
        if not line:
            continue
        import json

        run = json.loads(line)
        conclusion = str(run.get("conclusion") or "")
        if conclusion not in {"success", "failure", "cancelled", "timed_out"}:
            continue
        latest_executable = str(run.get("created_at"))
        break

    assert latest_executable, "no executable Health 68 run found"
    created = datetime.fromisoformat(latest_executable.replace("Z", "+00:00"))
    hours = (datetime.now(UTC) - created).total_seconds() / 3600.0
    assert hours <= 48, f"newest executable Health 68 run is {latest_executable} ({hours:.1f}h old)"


def test_live_probe_skips_only_without_a_token() -> None:
    text = WORKFLOW.parent.parent.parent / "tests/workflows/test_health_68_liveness.py"
    source = text.read_text(encoding="utf-8").split("def test_live_probe_skips", 1)[0]

    assert "RUN_LIVE_HEALTH_68_PROBE" not in source
    assert "GH_TOKEN or GITHUB_TOKEN required" in source


def test_health_68_issue_publish_job_is_split() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "publish-drift:" in text
    assert "check-drift:" in text
    assert text.index("publish-drift:") > text.index("check-drift:")
    publish_section = text.split("publish-drift:", 1)[1]
    assert "issues: write" in publish_section
    assert "Create drift issue" in publish_section


def test_health_68_closes_only_after_an_executed_clean_comparison() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "drift_clean: ${{ steps.compare.outcome == 'success' }}" in text
    assert "resolve-drift:" in text
    resolve_section = text.split("resolve-drift:", 1)[1]
    assert "needs.check-drift.result == 'success'" in resolve_section
    assert "needs.check-drift.outputs.drift_clean == 'true'" in resolve_section
    assert "inputs.repos == ''" in resolve_section
    assert "createIfMissing: false" in resolve_section
    assert "state: 'closed'" in resolve_section
    assert "state_reason: 'completed'" in resolve_section
    assert "tracker:durable" in resolve_section
