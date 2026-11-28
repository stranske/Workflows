"""Every dev-tool list derives from autofix-versions.env plus one package map (review B8).

Before 2026-11-28 the dev-tool list was kept by hand in six places that disagreed: Maint 50
(`maint_tool_version_check.py`) and `sync_tool_versions.py` never covered pytest-xdist.
Now `sync_dev_dependencies.DEV_TOOL_PACKAGES` is the only env-key -> package map, the
scripts derive their lists from the keys the env file pins, and this test pins the
one list that cannot import Python: the Renovate fleet preset's disabled dev-tool rule.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts import maint_tool_version_check, sync_tool_versions, update_versions_from_pypi
from scripts.sync_dev_dependencies import DEV_TOOL_PACKAGES, parse_env_file, pinned_dev_tools

ROOT = Path(__file__).resolve().parents[2]
PIN_FILE = ROOT / ".github/workflows/autofix-versions.env"
FLEET_PRESET = ROOT / "renovate-presets/fleet.json"
DEV_TOOL_RULE_MARKER = "Dev-tool pins are owned by autofix-versions.env"


def _pinned_packages() -> set[str]:
    return set(pinned_dev_tools(parse_env_file(PIN_FILE)).values())


def _fleet_dev_tool_rule() -> dict:
    preset = json.loads(FLEET_PRESET.read_text(encoding="utf-8"))
    rules = [
        rule
        for rule in preset.get("packageRules", [])
        if DEV_TOOL_RULE_MARKER in str(rule.get("description", ""))
    ]
    assert len(rules) == 1, "fleet.json must hold exactly one dev-tool ownership rule"
    return rules[0]


def test_every_pinned_key_has_a_package() -> None:
    pins = parse_env_file(PIN_FILE)
    version_keys = {key for key in pins if key.endswith("_VERSION")}
    assert version_keys, "autofix-versions.env pins no tools"
    assert version_keys <= set(DEV_TOOL_PACKAGES)


def test_unknown_pinned_key_fails_loudly() -> None:
    with pytest.raises(ValueError, match="NEWTOOL_VERSION"):
        pinned_dev_tools({"BLACK_VERSION": "1", "NEWTOOL_VERSION": "2"})


def test_pypi_updater_covers_exactly_the_pinned_tools() -> None:
    assert set(update_versions_from_pypi.PACKAGE_MAPPING.values()) == _pinned_packages()


def test_pyproject_aligner_covers_exactly_the_pinned_tools() -> None:
    assert {cfg.package_name for cfg in sync_tool_versions.TOOL_CONFIGS} == _pinned_packages()


def test_maint_50_reports_exactly_the_pinned_tools() -> None:
    assert {spec.package for spec in maint_tool_version_check.TOOLS} == _pinned_packages()
    assert "pytest-xdist" in {spec.package for spec in maint_tool_version_check.TOOLS}


def test_renovate_fleet_preset_disables_exactly_the_pinned_tools() -> None:
    """Pass number for B8: delete one name from fleet.json and this fails."""
    rule = _fleet_dev_tool_rule()
    assert rule.get("enabled") is False
    names = rule["matchPackageNames"]
    assert len(names) == len(set(names)), "duplicate dev-tool name in fleet.json"
    assert set(names) == _pinned_packages()
