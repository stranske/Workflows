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
    "maint-80-langsmith-metrics-dashboard.yml": (2415, 192),
    "maint-77-model-registry-freshness.yml": (2905, 192),
    "health-84-langsmith-observability.yml": (3123, 48),
    "health-40-repo-selfcheck.yml": (3218, 192),
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
        lambda _repo, workflow, _token, _events: runs[workflow],
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
            "latest_event": None,
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
            "latest_event": None,
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


def test_liveness_ignores_runs_whose_comparison_step_was_skipped(monkeypatch) -> None:
    """A run that concluded without running the work step is not evidence of life.

    Health 68's debounce skips the comparison steps while the JOB still concludes
    `success`, so the bare conclusion says only that the workflow was triggered.
    Measured live 2026-08-24: the seven newest `success` runs all had this step
    `skipped`, and the newest run that actually compared had FAILED four hours
    earlier — the oracle called that healthy.

    Two runs go in: a newer `success` whose step was skipped, and an older
    `success` whose step ran. The reported age must be measured from the OLDER one.
    """
    # THE WIRING, ASSERTED AGAINST THE SHIPPED CONFIG, NOT THE MONKEYPATCHED ONE.
    # The behaviour below is exercised through a stub config, so on its own it would
    # keep passing after `require_step` was deleted from the real file -- a gate that
    # cannot notice its own disconnection. Both halves have to be here.
    shipped = yaml.safe_load(LIVENESS_CONFIG.read_text(encoding="utf-8"))
    health_68 = next(
        entry
        for entry in shipped.get("execution_liveness") or []
        if entry["workflow"] == "health-68-consumer-sync-drift.yml"
    )
    assert health_68.get("require_step") == "Compare consumer repos to templates", (
        "health-68 has no require_step in the shipped config, so in production the "
        "checker is back to reading the bare job conclusion"
    )

    newer = {
        "id": 2,
        "conclusion": "success",
        "created_at": "2026-08-24T22:18:09Z",
        "html_url": "https://run/newer",
    }
    older = {
        "id": 1,
        "conclusion": "success",
        "created_at": "2026-08-24T20:29:59Z",
        "html_url": "https://run/older",
    }
    step_conclusions = {2: "skipped", 1: "success"}

    monkeypatch.setattr(
        check_durable_tracker_liveness,
        "_load_config",
        lambda: [
            {
                "workflow": "health-68-consumer-sync-drift.yml",
                "issue": None,
                "max_age_hours": 48,
                "require_step": "Compare consumer repos to templates",
                "durable": False,
            }
        ],
    )
    monkeypatch.setattr(
        check_durable_tracker_liveness,
        "_gh_api",
        lambda path, _token: {"workflow_runs": [newer, older]},
    )
    monkeypatch.setattr(
        check_durable_tracker_liveness,
        "run_step_conclusion",
        lambda _repo, run_id, _step, _token: step_conclusions[run_id],
    )
    ages = {"2026-08-24T22:18:09Z": 1.0, "2026-08-24T20:29:59Z": 3.0}
    monkeypatch.setattr(check_durable_tracker_liveness, "_hours_since", lambda ts: ages[ts])

    (result,) = check_durable_tracker_liveness.evaluate_trackers("stranske/Workflows", "token")

    # The bare run age still reports the NEWER run -- both numbers are published.
    assert result["latest_created_at"] == newer["created_at"]
    assert result["hours_since"] == 1.0
    # Liveness is measured from the OLDER run, the one that actually compared.
    assert result["latest_executing_created_at"] == older["created_at"]
    assert result["hours_since_executing_run"] == 3.0
    assert result["required_step_conclusion"] == "success"


def test_liveness_says_so_when_nothing_in_history_ran_the_step(monkeypatch) -> None:
    """ "Ran and compared nothing" must not be silently reported as an age.

    The fix for #3243 must not rebuild #3243 one level up: when no run in the probed
    window executed the required step, the checker has to SAY that, not fall back to
    the bare run age and look healthy.
    """
    runs = [
        {"id": n, "conclusion": "success", "created_at": f"2026-08-24T2{n}:00:00Z"}
        for n in range(3)
    ]
    monkeypatch.setattr(
        check_durable_tracker_liveness,
        "_load_config",
        lambda: [
            {
                "workflow": "health-68-consumer-sync-drift.yml",
                "issue": None,
                "max_age_hours": 48,
                "require_step": "Compare consumer repos to templates",
                "durable": False,
            }
        ],
    )
    monkeypatch.setattr(
        check_durable_tracker_liveness, "_gh_api", lambda path, _token: {"workflow_runs": runs}
    )
    monkeypatch.setattr(
        check_durable_tracker_liveness,
        "run_step_conclusion",
        lambda _repo, _run_id, _step, _token: "skipped",
    )
    monkeypatch.setattr(check_durable_tracker_liveness, "_hours_since", lambda _ts: 0.1)

    (result,) = check_durable_tracker_liveness.evaluate_trackers("stranske/Workflows", "token")

    assert result["healthy"] is False, "0.1h since a no-op run must not read as healthy"
    assert result["hours_since_executing_run"] is None
    assert result["latest_executing_created_at"] is None
    assert "Compare consumer repos to templates" in result["reason"]
    assert "triggered, not that it executed" in result["reason"]


def test_run_step_conclusion_distinguishes_absent_from_skipped(monkeypatch) -> None:
    """`None` (no such step) and `"skipped"` (step ran, was skipped) are different facts."""
    payload = {
        "jobs": [
            {
                "name": "Validate consumer repo drift",
                "steps": [
                    {"name": "Debounce workflow_run fan-out", "conclusion": "success"},
                    {"name": "Compare consumer repos to templates", "conclusion": "skipped"},
                ],
            }
        ]
    }
    monkeypatch.setattr(check_durable_tracker_liveness, "_gh_api", lambda _p, _t: payload)

    assert (
        check_durable_tracker_liveness.run_step_conclusion(
            "o/r", 1, "Compare consumer repos to templates", "t"
        )
        == "skipped"
    )
    assert check_durable_tracker_liveness.run_step_conclusion("o/r", 1, "No Such Step", "t") is None


def test_execution_liveness_entries_are_excluded_from_tracker_doc_coverage() -> None:
    """An execution-only entry must not be required to have a durable-tracker row.

    #2210 is a TRANSIENT alert Health 68 opens and closes, and it is currently
    closed. Listing health-68 under `trackers:` would assert a durable relationship
    that does not exist.
    """
    config = yaml.safe_load(LIVENESS_CONFIG.read_text(encoding="utf-8"))
    execution_only = {str(entry["workflow"]) for entry in config.get("execution_liveness") or []}
    assert "health-68-consumer-sync-drift.yml" in execution_only

    durable = check_durable_tracker_liveness._durable_tracker_workflows()
    assert "health-68-consumer-sync-drift.yml" not in durable
    assert durable == tracker_doc_workflows()

    entry = next(
        item
        for item in config["execution_liveness"]
        if item["workflow"] == "health-68-consumer-sync-drift.yml"
    )
    assert entry["require_step"] == "Compare consumer repos to templates"
    assert entry["issue"] is None, "a transient alert is not a durable tracker to comment on"


def test_health_71_invokes_durable_tracker_liveness_check() -> None:
    text = HEALTH_71.read_text(encoding="utf-8")
    assert "check_durable_tracker_liveness.py" in text
    assert "--comment-on-failure" in text


def test_model_registry_liveness_counts_only_tracker_publishing_events() -> None:
    config = yaml.safe_load(LIVENESS_CONFIG.read_text(encoding="utf-8"))
    tracker = next(
        entry
        for entry in config["trackers"]
        if entry["workflow"] == "maint-77-model-registry-freshness.yml"
    )

    assert tracker["events"] == ["schedule", "workflow_dispatch"]


def test_latest_executable_run_queries_publishing_events_before_history_limit(
    monkeypatch,
) -> None:
    seen: list[str] = []
    scheduled = {
        "event": "schedule",
        "conclusion": "success",
        "created_at": "2026-08-20T00:00:00Z",
    }
    dispatched = {
        "event": "workflow_dispatch",
        "conclusion": "success",
        "created_at": "2026-08-21T00:00:00Z",
    }

    def fake_gh_api(path: str, _token: str) -> dict[str, object]:
        seen.append(path)
        if "event=schedule" in path:
            return {"workflow_runs": [scheduled]}
        if "event=workflow_dispatch" in path:
            return {"workflow_runs": [dispatched]}
        raise AssertionError(f"unfiltered run history requested: {path}")

    monkeypatch.setattr(check_durable_tracker_liveness, "_gh_api", fake_gh_api)

    latest = check_durable_tracker_liveness._latest_executable_run(
        "stranske/Workflows",
        "maint-77-model-registry-freshness.yml",
        "token",
        frozenset({"schedule", "workflow_dispatch"}),
    )

    assert latest == dispatched
    assert seen == [
        "repos/stranske/Workflows/actions/workflows/maint-77-model-registry-freshness.yml/"
        "runs?per_page=100&event=schedule&page=1",
        "repos/stranske/Workflows/actions/workflows/maint-77-model-registry-freshness.yml/"
        "runs?per_page=100&event=workflow_dispatch&page=1",
    ]


def test_latest_executable_run_paginates_event_filtered_history(monkeypatch) -> None:
    held_runs = [{"conclusion": "action_required"} for _ in range(100)]
    executable = {
        "event": "schedule",
        "conclusion": "success",
        "created_at": "2026-08-20T00:00:00Z",
    }
    seen: list[str] = []

    def fake_gh_api(path: str, _token: str) -> dict[str, object]:
        seen.append(path)
        return {"workflow_runs": held_runs if path.endswith("&page=1") else [executable]}

    monkeypatch.setattr(check_durable_tracker_liveness, "_gh_api", fake_gh_api)

    latest = check_durable_tracker_liveness._latest_executable_run(
        "stranske/Workflows",
        "maint-77-model-registry-freshness.yml",
        "token",
        frozenset({"schedule"}),
    )

    assert latest == executable
    assert seen[-1].endswith("event=schedule&page=2")


def test_execution_liveness_requires_main_branch_runs(monkeypatch) -> None:
    """Health 68's required-step evidence must describe the production branch."""
    seen: list[str] = []
    run = {
        "id": 7,
        "conclusion": "success",
        "created_at": "main-run",
        "html_url": "https://run/main",
    }

    monkeypatch.setattr(
        check_durable_tracker_liveness,
        "_load_config",
        lambda: [
            {
                "workflow": "health-68-consumer-sync-drift.yml",
                "issue": None,
                "max_age_hours": 48,
                "require_step": "Compare consumer repos to templates",
                "durable": False,
            }
        ],
    )
    monkeypatch.setattr(
        check_durable_tracker_liveness,
        "_gh_api",
        lambda path, _token: seen.append(path) or {"workflow_runs": [run]},
    )
    monkeypatch.setattr(
        check_durable_tracker_liveness,
        "run_step_conclusion",
        lambda *_args: "success",
    )
    monkeypatch.setattr(check_durable_tracker_liveness, "_hours_since", lambda _ts: 1.0)

    (result,) = check_durable_tracker_liveness.evaluate_trackers("stranske/Workflows", "token")

    assert result["healthy"] is True
    assert any("branch=main" in path for path in seen)


def test_require_step_probe_budget_spans_paginated_history(monkeypatch) -> None:
    """A page boundary must not reset the fixed step-probe budget."""
    first_page = [
        {"id": index, "conclusion": "success", "created_at": f"first-{index}"}
        for index in range(10)
    ] + [{"conclusion": "queued"} for _ in range(90)]
    second_page = [
        {"id": 100 + index, "conclusion": "success", "created_at": f"second-{index}"}
        for index in range(100)
    ]
    seen_paths: list[str] = []
    probed: list[int] = []

    def fake_gh_api(path: str, _token: str) -> dict[str, object]:
        seen_paths.append(path)
        return {"workflow_runs": second_page if path.endswith("&page=2") else first_page}

    def all_skipped(_repo: str, run_id: int, _step: str, _token: str) -> str:
        probed.append(run_id)
        return "skipped"

    monkeypatch.setattr(check_durable_tracker_liveness, "_gh_api", fake_gh_api)
    monkeypatch.setattr(check_durable_tracker_liveness, "run_step_conclusion", all_skipped)

    latest = check_durable_tracker_liveness._latest_executable_run(
        "stranske/Workflows",
        "health-68-consumer-sync-drift.yml",
        "token",
        require_step="Compare consumer repos to templates",
    )

    assert latest is None
    assert any(path.endswith("&page=2") for path in seen_paths)
    assert len(probed) == check_durable_tracker_liveness.STEP_PROBE_LIMIT


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
