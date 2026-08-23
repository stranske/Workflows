"""Offline gate: every durable tracker workflow has a Health 71 liveness assertion."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from scripts import check_durable_tracker_liveness
from scripts.check_durable_tracker_liveness import tracker_doc_workflows

TRACKER_DOC = Path("docs/ops/DURABLE_TRACKING_ISSUES.md")
LIVENESS_CONFIG = Path("config/durable_tracker_liveness.yml")
HEALTH_71 = Path(".github/workflows/health-71-sync-health-check.yml")

EXPECTED_TRACKERS = {
    "agents-weekly-metrics.yml": (2211, 192),
    "maint-82-sync-dependency-campaign.yml": (1836, 1),
    "health-83-dependency-sync-efficiency.yml": (2897, 192),
    "health-68-consumer-sync-drift.yml": (2210, 48),
    "maint-69-sync-integration-repo.yml": (2470, None),
    "maint-80-langsmith-metrics-dashboard.yml": (2415, 192),
}


def _configured_workflows() -> set[str]:
    config = yaml.safe_load(LIVENESS_CONFIG.read_text(encoding="utf-8"))
    return {str(entry["workflow"]) for entry in config["trackers"]}


def test_every_tracked_workflow_has_a_liveness_assertion() -> None:
    documented = tracker_doc_workflows()
    configured = _configured_workflows()
    missing = sorted(documented - configured)
    extra = sorted(configured - documented)
    assert not missing, f"tracker table workflows missing liveness config: {missing}"
    assert not extra, f"liveness config has undocumented workflows: {extra}"


def test_liveness_config_has_literal_expected_tracker_contract() -> None:
    config = yaml.safe_load(LIVENESS_CONFIG.read_text(encoding="utf-8"))
    observed = {
        entry["workflow"]: (int(entry["issue"]), entry.get("max_age_hours"))
        for entry in config["trackers"]
    }
    assert observed == EXPECTED_TRACKERS


def test_evaluate_trackers_classifies_event_driven_recent_stale_and_absent_runs(
    monkeypatch,
) -> None:
    trackers = [
        {"workflow": "event.yml", "issue": 1, "event_driven": True},
        {"workflow": "recent.yml", "issue": 2, "max_age_hours": 24},
        {"workflow": "stale.yml", "issue": 3, "max_age_hours": 24},
        {"workflow": "absent.yml", "issue": 4, "max_age_hours": 24},
    ]
    runs = {
        "recent.yml": {
            "conclusion": "success",
            "created_at": "recent",
            "html_url": "https://run/recent",
        },
        "stale.yml": {
            "conclusion": "failure",
            "created_at": "stale",
            "html_url": "https://run/stale",
        },
        "absent.yml": None,
    }
    monkeypatch.setattr(check_durable_tracker_liveness, "_load_config", lambda: trackers)
    monkeypatch.setattr(
        check_durable_tracker_liveness,
        "_latest_executable_run",
        lambda _repo, workflow, _token: runs[workflow],
    )
    monkeypatch.setattr(
        check_durable_tracker_liveness,
        "_hours_since",
        lambda created: 1.0 if created == "recent" else 25.0,
    )

    assert check_durable_tracker_liveness.evaluate_trackers("stranske/Workflows", "token") == [
        {
            "workflow": "event.yml",
            "issue": 1,
            "healthy": True,
            "reason": "event-driven workflow excluded from age-based liveness",
        },
        {
            "workflow": "recent.yml",
            "issue": 2,
            "healthy": True,
            "latest_conclusion": "success",
            "latest_created_at": "recent",
            "hours_since": 1.0,
            "max_age_hours": 24.0,
            "run_url": "https://run/recent",
        },
        {
            "workflow": "stale.yml",
            "issue": 3,
            "healthy": False,
            "latest_conclusion": "failure",
            "latest_created_at": "stale",
            "hours_since": 25.0,
            "max_age_hours": 24.0,
            "run_url": "https://run/stale",
        },
        {
            "workflow": "absent.yml",
            "issue": 4,
            "healthy": False,
            "reason": ABSENT_REASON,
        },
    ]


def test_health_71_invokes_durable_tracker_liveness_check() -> None:
    text = HEALTH_71.read_text(encoding="utf-8")
    assert "check_durable_tracker_liveness.py" in text
    assert "--comment-on-failure" in text


def test_event_driven_tracker_is_not_subject_to_age_liveness() -> None:
    config = yaml.safe_load(LIVENESS_CONFIG.read_text(encoding="utf-8"))
    tracker = next(
        entry
        for entry in config["trackers"]
        if entry["workflow"] == "maint-69-sync-integration-repo.yml"
    )

    assert tracker["event_driven"] is True
    assert "max_age_hours" not in tracker


# The absent-run reason now also names the cause and the remedy: "no executable
# run found" is true but unactionable, and the cause is almost always GitHub's
# suspicious-workflow protection, which no REST endpoint can clear.
ABSENT_REASON = (
    "no executable run found (only action_required/skipped)."
    + check_durable_tracker_liveness._held_by_workflow_protection(
        True, "stranske/Workflows", "absent.yml"
    )
)


def test_tracker_run_lookup_goes_through_the_sanctioned_wrapper(monkeypatch) -> None:
    """The probe must not shell out to the raw API.

    scripts/check_api_wrapper_guard.py forbids that in scripts/, and CI enforces
    it - this PR was rejected once for exactly that. Replaces an older test that
    asserted the shell-out forced GET; the wrapper owns the HTTP method now, and
    reusing it also gives this probe the pacing and backoff it never had.
    """
    seen: list[str] = []

    def fake_gh_api(path: str, token: str | None = None) -> dict[str, object]:
        seen.append(path)
        return {"workflow_runs": []}

    monkeypatch.setattr(check_durable_tracker_liveness, "_gh_api", fake_gh_api)

    assert (
        check_durable_tracker_liveness._latest_executable_run(
            "stranske/Workflows", "health-68-consumer-sync-drift.yml", "token"
        )
        is None
    )
    assert seen == [
        "repos/stranske/Workflows/actions/workflows/"
        "health-68-consumer-sync-drift.yml/runs?per_page=100"
    ]


def test_tracker_doc_table_links_match_config() -> None:
    text = TRACKER_DOC.read_text(encoding="utf-8")
    section_match = re.search(
        r"## Current durable trackers\n\n\| Issue.*?\n\|[-| ]+\n(.*?)(?:\n\n|\n### )",
        text,
        re.DOTALL,
    )
    assert section_match
    issue_to_workflow: dict[int, str] = {}
    for row in section_match.group(1).splitlines():
        issue_match = re.search(r"\[#(\d+)\]", row)
        workflow_match = re.search(r"/([^/)]+?\.yml)\)", row)
        if issue_match and workflow_match:
            issue_to_workflow[int(issue_match.group(1))] = workflow_match.group(1)
    config = yaml.safe_load(LIVENESS_CONFIG.read_text(encoding="utf-8"))
    for entry in config["trackers"]:
        issue = int(entry["issue"])
        workflow = str(entry["workflow"])
        assert issue_to_workflow.get(issue) == workflow, (
            f"config issue #{issue} maps to {workflow}, "
            f"tracker doc maps to {issue_to_workflow.get(issue)}"
        )


# --- probe robustness (added 2026-08-23) ---------------------------------
#
# The probe originally shelled to `gh` with no retry, so one GitHub SECONDARY
# rate-limit 403 -- a separate cap on rapid sequential requests, invisible to
# /rate_limit -- raised CalledProcessError and aborted the whole liveness check.
# The sweep hit the same trap. A liveness checker that dies on API noise reports
# nothing, which is the failure it exists to prevent.


def test_hold_is_named_not_just_reported_as_missing() -> None:
    """ "no executable run" is true but unactionable; name the hold and the remedy."""
    import scripts.check_durable_tracker_liveness as mod

    msg = mod._held_by_workflow_protection(True, "owner/repo", "health-68.yml")

    assert "suspicious-workflow protection" in msg
    assert "Approve and run" in msg
    assert "No REST endpoint clears it" in msg
    assert mod._held_by_workflow_protection(False, "owner/repo", "health-68.yml") == ""


def test_api_failure_propagates_instead_of_looking_healthy(monkeypatch) -> None:
    """A failed lookup must not read as "no executable run".

    Returning None on an API error would blame the workflow for the checker's own
    inability to look. The wrapper raises; this pins that the probe does not
    swallow it.
    """

    def boom(path: str, token: str | None = None):
        raise RuntimeError("GitHub API error 403: rate limit")

    monkeypatch.setattr(check_durable_tracker_liveness, "_gh_api", boom)

    try:
        check_durable_tracker_liveness._latest_executable_run("o/r", "wf.yml", "t")
    except RuntimeError as exc:
        assert "403" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected the API failure to propagate")
