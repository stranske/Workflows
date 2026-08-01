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
    assert preset["schedule"] == ["after 1am and before 5am on monday"]
    assert preset["commitHourlyLimit"] == 2
    assert preset["prConcurrentLimit"] == 3
    assert preset["branchConcurrentLimit"] == 3
    assert preset["prCreation"] == "not-pending"
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
        "schedule": ["after 1am and before 5am on monday"],
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
