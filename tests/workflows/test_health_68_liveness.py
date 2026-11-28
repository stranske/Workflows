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


def _job_if_selected(condition: str, context: dict[str, str]) -> bool:
    condition = " ".join(condition.strip().removeprefix("${{").removesuffix("}}").split())
    for key in sorted(context, key=len, reverse=True):
        condition = condition.replace(key, repr(context[key]))
    return eval(  # noqa: S307 - local authored expressions with fixed scalar contexts
        condition.replace("always()", "True").replace("&&", " and ").replace("||", " or "),
        {"__builtins__": {}},
    )


def test_measures_on_the_drain_cadence_not_on_push() -> None:
    """Round-2 A2: Maint 68 drains on its schedule, so a push is not drift yet.

    The push trigger re-measured undelivered work on every merge and opened 15 drift
    issues between 11-12 and 11-28 that the next Maint 68 run delivered anyway.
    """
    triggers = _workflow_triggers()
    assert "push" not in triggers
    assert set(triggers) == {"workflow_run", "schedule", "workflow_dispatch"}


@pytest.mark.parametrize(
    ("event", "upstream_event", "conclusion", "branch", "runs"),
    [
        ("schedule", "", "", "", True),
        ("workflow_dispatch", "", "", "", True),
        ("workflow_run", "schedule", "success", "main", True),
        # Dispatched Maint 71 continuations end the run `skipped`, never `success`.
        ("workflow_run", "repository_dispatch", "success", "main", False),
        ("workflow_run", "workflow_dispatch", "success", "main", False),
        ("workflow_run", "schedule", "failure", "main", False),
        ("workflow_run", "schedule", "success", "feature", False),
    ],
)
def test_only_comparing_runs_reach_the_job(event, upstream_event, conclusion, branch, runs) -> None:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    context = {
        "github.event_name": event,
        "github.event.workflow_run.event": upstream_event,
        "github.event.workflow_run.conclusion": conclusion,
        "github.event.workflow_run.head_branch": branch,
    }
    assert _job_if_selected(data["jobs"]["check-drift"]["if"], context) is runs


def test_no_step_can_skip_the_comparison_inside_a_running_job() -> None:
    """A job that runs must compare: no debounce, no step-level skip of the compare."""
    text = WORKFLOW.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    steps = {step["name"]: step for step in data["jobs"]["check-drift"]["steps"]}
    assert "if" not in steps[COMPARE_STEP]
    assert "steps.debounce" not in text
    assert "actions/cache/" not in text


def test_comparison_reads_the_drain_history() -> None:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = data["jobs"]["check-drift"]["steps"]
    names = [step["name"] for step in steps]
    history = names.index("Read Maint 68 delivery history")
    assert history < names.index(COMPARE_STEP)
    assert "--write-deliveries artifacts/maint-68-deliveries.json" in steps[history]["run"]
    compare = next(step for step in steps if step["name"] == COMPARE_STEP)
    assert compare["env"]["CONSUMER_SYNC_DELIVERIES_JSON"] == "artifacts/maint-68-deliveries.json"


@pytest.mark.parametrize(
    ("repos", "outcome", "publishes", "resolves"),
    [
        ("stranske/trip-planner", "failure", False, False),
        ("stranske/trip-planner", "success", False, False),
        ("", "failure", True, False),
        ("", "success", False, True),
    ],
)
def test_manual_repo_scope_does_not_write_fleet_state(repos, outcome, publishes, resolves) -> None:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = data["jobs"]
    context = {
        "inputs.repos": repos,
        "needs.check-drift.result": outcome,
        "needs.check-drift.outputs.drift_failed": str(outcome == "failure").lower(),
        "needs.check-drift.outputs.drift_clean": str(outcome == "success").lower(),
    }
    assert _job_if_selected(jobs["publish-drift"]["if"], context) is publishes
    assert _job_if_selected(jobs["resolve-drift"]["if"], context) is resolves


def test_manual_repo_scope_has_run_specific_concurrency() -> None:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    group = " ".join(data["concurrency"]["group"].split())
    assert "inputs.repos != ''" in group
    assert "format('health-68-consumer-sync-drift-scoped-{0}', github.run_id)" in group
    assert group.endswith("|| 'health-68-consumer-sync-drift' }}")
    assert data["concurrency"]["cancel-in-progress"] is True


def test_liveness_config_names_the_compare_step() -> None:
    """The durable liveness probe must still inspect the actual compare step."""
    import yaml as _yaml

    text = WORKFLOW.read_text(encoding="utf-8")
    data = _yaml.safe_load(text)
    steps = data["jobs"]["check-drift"]["steps"]
    step_names = [str(step.get("name") or "") for step in steps]
    assert COMPARE_STEP in step_names, "the step the liveness probe measures must exist"

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
