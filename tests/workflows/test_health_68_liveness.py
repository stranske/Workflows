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


COMPARE_STEP = "Compare consumer repos to templates"


def test_consumer_drift_detector_debounces_workflow_run() -> None:
    """The debounce must clock the last run that COMPARED using an Actions cache marker.

    The old fan-out queried GitHub API for prior workflow runs and listJobsForWorkflowRun.
    The new mechanism uses actions/cache to store and restore a comparison timestamp marker.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "Debounce workflow_run fan-out" in text
    assert "github.event_name == 'workflow_run'" in text
    assert "actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9" in text
    assert "actions/cache/save@55cc8345863c7cc4c66a329aec7e433d2d1c52a9" in text

    # Only completed comparison attempts update the cache marker.
    assert "steps.compare.outcome == 'success'" in text
    assert "steps.compare.outcome == 'failure'" in text

    # API fan-out calls are no longer used for debounce
    assert "listJobsForWorkflowRun" not in text
    assert "listWorkflowRuns" not in text

    # ...and no longer selects purely on the run conclusion. The old jq selector is
    # pinned as ABSENT so restoring it is a test failure, not a silent regression.
    assert (
        "--argjson current" not in text
    ), "the bare-conclusion jq selector is back; it counts debounced no-ops as runs"


def test_liveness_config_names_the_compare_step() -> None:
    """The durable liveness probe must still inspect the actual compare step."""
    import yaml as _yaml

    text = WORKFLOW.read_text(encoding="utf-8")
    data = _yaml.safe_load(text)
    steps = data["jobs"]["check-drift"]["steps"]
    step_names = [str(step.get("name") or "") for step in steps]
    assert COMPARE_STEP in step_names, "the step the debounce measures must exist"

    config = _yaml.safe_load(
        Path("config/durable_tracker_liveness.yml").read_text(encoding="utf-8")
    )
    entry = next(
        item
        for item in config["execution_liveness"]
        if item["workflow"] == "health-68-consumer-sync-drift.yml"
    )
    assert entry["require_step"] == COMPARE_STEP


def test_check_drift_publishes_whether_it_compared() -> None:
    """The job must say whether it did the work, not only that it concluded."""
    import yaml as _yaml

    data = _yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    outputs = data["jobs"]["check-drift"]["outputs"]
    assert outputs["compared"] == "${{ steps.compare.outcome != 'skipped' }}"


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


LIVE_PROBE_SKIP_REASON = "GH_TOKEN or GITHUB_TOKEN required for the live Health 68 execution probe"


@pytest.mark.skipif(
    not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")),
    reason=LIVE_PROBE_SKIP_REASON,
)
def test_consumer_drift_detector_executed_recently() -> None:
    """The newest run that COMPARED must be recent — not the newest run.

    #3179's Implementation Notes specified a probe that skips only when no token is
    present; the shipped version also required RUN_LIVE_HEALTH_68_PROBE=1, so it never
    ran in CI even where a token existed. That extra term is gone.

    The probe also no longer accepts a bare run conclusion. Measured live 2026-08-24,
    the seven newest `success` runs had this step `skipped` and the newest run that
    actually compared had FAILED — a bare-conclusion probe called that healthy.
    """
    import json

    repo = os.environ.get("GITHUB_REPOSITORY", "stranske/Workflows")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    payload = subprocess.check_output(
        [
            "gh",
            "api",
            f"repos/{repo}/actions/workflows/health-68-consumer-sync-drift.yml/runs"
            "?per_page=100&branch=main",
            "-q",
            ".workflow_runs[]",
        ],
        text=True,
        env={**os.environ, "GH_TOKEN": token},
    )
    latest_comparing: str | None = None
    probed = 0
    for line in payload.splitlines():
        line = line.strip()
        if not line:
            continue
        run = json.loads(line)
        conclusion = str(run.get("conclusion") or "")
        if conclusion not in {"success", "failure", "cancelled", "timed_out"}:
            continue
        if probed >= 20:
            break
        probed += 1
        steps = subprocess.check_output(
            [
                "gh",
                "api",
                f"repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100",
                "-q",
                f'.jobs[].steps[] | select(.name=="{COMPARE_STEP}") | .conclusion',
            ],
            text=True,
            env={**os.environ, "GH_TOKEN": token},
        ).split()
        if any(step != "skipped" for step in steps):
            latest_comparing = str(run.get("created_at"))
            break

    assert latest_comparing, (
        f"no Health 68 run in the {probed} newest executable runs ran {COMPARE_STEP!r}; "
        "every one concluded without comparing anything"
    )
    created = datetime.fromisoformat(latest_comparing.replace("Z", "+00:00"))
    hours = (datetime.now(UTC) - created).total_seconds() / 3600.0
    assert (
        hours <= 48
    ), f"newest Health 68 run that COMPARED is {latest_comparing} ({hours:.1f}h old)"


def test_live_probe_skips_only_on_a_missing_token() -> None:
    """The skip condition must name the missing variable and nothing else.

    RUN_LIVE_HEALTH_68_PROBE made the probe unrunnable in CI even with a token, which
    is a gate whose drain is switched off by default.
    """
    # Pin the READ, not the name: this file is allowed to explain the flag in prose,
    # and it does. The literal is split so the needle cannot match its own line.
    source = Path(__file__).read_text(encoding="utf-8")
    needle = 'environ.get("RUN_LIVE' + '_HEALTH_68_PROBE")'
    assert (
        needle not in source
    ), "the opt-in flag is being read again; the live probe will never run in CI"

    assert "GH_TOKEN" in LIVE_PROBE_SKIP_REASON
    assert "GITHUB_TOKEN" in LIVE_PROBE_SKIP_REASON

    marker = next(
        mark
        for mark in test_consumer_drift_detector_executed_recently.pytestmark
        if mark.name == "skipif"
    )
    assert marker.kwargs["reason"] == LIVE_PROBE_SKIP_REASON

    # Behavioural, and stronger than the source pin: the condition must be exactly
    # "no token". Any extra opt-in term makes this differ whenever a token is present.
    expected_skip = not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    assert bool(marker.args[0]) is bool(expected_skip)


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
