import json
from pathlib import Path

PRESET_PATH = Path(__file__).resolve().parents[2] / "renovate-presets" / "fleet.json"
REPO_ROOT = PRESET_PATH.parents[1]


def _preset() -> dict:
    return json.loads(PRESET_PATH.read_text(encoding="utf-8"))


def _rule(preset: dict, **expected: object) -> dict:
    matches = [
        rule
        for rule in preset["packageRules"]
        if all(rule.get(key) == value for key, value in expected.items())
    ]
    assert len(matches) == 1
    return matches[0]


def test_fleet_renovate_intake_budget_is_bounded_to_the_weekly_window() -> None:
    preset = _preset()

    assert preset["timezone"] == "America/Chicago"
    # The window must be wider than the gap between Mend's hosted runs. On 11-23 all three
    # sampled consumer dashboards were edited at 06:38-06:39Z and next at 11:56Z or later, so
    # no run fell inside the old 4-hour window (01:00-05:00 Chicago = 07:00-11:00Z) and no
    # branch moved that week. The widest edit gap seen 11-15..11-28 was about 12h; all of
    # Monday (24h) covers it. Intake stays bounded by the hourly and concurrency limits.
    assert preset["schedule"] == ["on monday"]
    assert preset["commitHourlyLimit"] == 2
    assert preset["prConcurrentLimit"] == 3
    assert preset["branchConcurrentLimit"] == 3
    # Consumer Gate runs only on pull_request, so a Renovate branch push gets no checks of its
    # own (only Renovate's internal stability-days status). "not-pending" therefore waited
    # forever for checks that only a PR starts: consumers opened 0 Renovate PRs from 08-01
    # to 11-28 while their branches kept being refreshed. Open the PR at once.
    assert preset["prCreation"] == "immediate"
    assert preset["minimumReleaseAge"] == "3 days"


def test_trusted_action_digests_are_grouped() -> None:
    rule = _rule(_preset(), matchManagers=["github-actions"])

    assert rule["matchUpdateTypes"] == ["digest", "pin", "minor", "patch"]
    assert rule["groupName"] == "github-actions"
    assert rule["automerge"] is True


def test_fleet_preset_keeps_workflows_owned_dev_tool_pins_out_of_renovate() -> None:
    rule = _rule(_preset(), enabled=False)

    assert rule["matchPackageNames"] == [
        "ruff",
        "black",
        "mypy",
        "pytest",
        "pytest-cov",
        "pytest-xdist",
        "coverage",
        "isort",
        "docformatter",
    ]


def test_vulnerability_alerts_bypass_routine_intake_delays() -> None:
    alerts = _preset()["vulnerabilityAlerts"]

    assert alerts == {
        "schedule": [],
        "minimumReleaseAge": None,
        "prCreation": "immediate",
    }


def test_major_updates_stay_visible_but_require_dashboard_approval() -> None:
    preset = _preset()
    rule = _rule(preset, matchUpdateTypes=["major"])

    assert preset["dependencyDashboard"] is True
    assert rule["dependencyDashboardApproval"] is True
    assert rule["automerge"] is False


def test_lock_file_maintenance_has_the_same_explicit_weekly_cadence() -> None:
    lock_maintenance = _preset()["lockFileMaintenance"]

    assert lock_maintenance == {
        "enabled": True,
        "groupName": "weekly lock file maintenance",
        "schedule": _preset()["schedule"],
    }


def test_workflows_and_consumer_entrypoints_share_the_bounded_fleet_policy() -> None:
    expected_preset = "github>stranske/Workflows//renovate-presets/fleet"
    entrypoints = (
        REPO_ROOT / "renovate.json",
        REPO_ROOT / "templates" / "consumer-repo" / ".github" / "renovate.json",
    )

    for entrypoint in entrypoints:
        config = json.loads(entrypoint.read_text(encoding="utf-8"))
        assert config["extends"] == [expected_preset]

    preset = _preset()
    assert preset["prConcurrentLimit"] == preset["branchConcurrentLimit"] == 3


def test_workflows_dependency_updates_preserve_reviewed_runtime_and_packets() -> None:
    config = json.loads((REPO_ROOT / "renovate.json").read_text())
    assert "config/verify_paired/**" in config["ignorePaths"]
    assert ".github/actions/trial-codex-cli/**" in config["ignorePaths"]
    trial_freeze = _rule(
        config,
        matchFileNames=[".github/actions/trial-codex-cli/**"],
        enabled=False,
    )
    assert set(trial_freeze) <= {"description", "matchFileNames", "enabled"}
    runtime = _rule(config, matchManagers=["github-actions"], matchPackageNames=["python"])
    assert runtime["allowedVersions"] == "<3.15"


def test_workflows_has_no_private_pr_creation_override() -> None:
    """The fleet preset is the one writer of prCreation; Workflows used to override it alone."""
    workflows_config = json.loads((REPO_ROOT / "renovate.json").read_text(encoding="utf-8"))
    rules = workflows_config.get("packageRules", [])
    assert all("prCreation" not in rule for rule in rules)
    assert "prCreation" not in workflows_config
