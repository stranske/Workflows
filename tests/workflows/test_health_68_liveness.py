"""Offline gates for Health 68 trigger and execution liveness."""

from __future__ import annotations

import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(".github/workflows/health-68-consumer-sync-drift.yml")
TRACKER_DOC = Path("docs/ops/DURABLE_TRACKING_ISSUES.md")
LIVENESS_CONFIG = Path("config/durable_tracker_liveness.yml")


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
    assert "--jq '[.workflow_runs[]" in text
    assert ".conclusion == \"cancelled\"" not in text


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


def test_health_68_issue_publish_job_is_split() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "publish-drift:" in text
    assert "check-drift:" in text
    assert text.index("publish-drift:") > text.index("check-drift:")
    publish_section = text.split("publish-drift:", 1)[1]
    assert "issues: write" in publish_section
    assert "Create drift issue" in publish_section


def test_tracker_doc_lists_daily_schedule_for_health_68() -> None:
    text = TRACKER_DOC.read_text(encoding="utf-8")
    row = re.search(
        r"\| \[#2210\].*?\|.*?\|.*?\| (.*?) \|",
        text,
        re.DOTALL,
    )
    assert row, "missing #2210 cadence row"
    cadence = row.group(1)
    assert "schedule" in cadence.lower() or "daily" in cadence.lower()


def test_liveness_config_includes_health_68() -> None:
    config = yaml.safe_load(LIVENESS_CONFIG.read_text(encoding="utf-8"))
    workflows = {entry["workflow"] for entry in config["trackers"]}
    assert "health-68-consumer-sync-drift.yml" in workflows
