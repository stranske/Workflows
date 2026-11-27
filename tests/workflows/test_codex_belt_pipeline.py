"""Verify retirement of the hosted belt and its matching consumer workflows."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = Path(".github/workflows")
TEMPLATE = ROOT / "templates/consumer-repo"
RETIRED_CONSUMER_WORKFLOWS = (
    "agents-71-codex-belt-dispatcher.yml",
    "agents-72-codex-belt-worker-dispatch.yml",
    "agents-72-codex-belt-worker.yml",
    "agents-73-codex-belt-conveyor.yml",
)


@pytest.mark.parametrize("name", RETIRED_CONSUMER_WORKFLOWS)
def test_retired_belt_workflow_is_removed_from_host_and_consumers(name: str) -> None:
    relative = WORKFLOWS / name
    assert not (ROOT / relative).exists()
    assert not (TEMPLATE / relative).exists()

    manifest = yaml.safe_load((ROOT / ".github/sync-manifest.yml").read_text(encoding="utf-8"))
    assert not any(entry["source"] == relative.as_posix() for entry in manifest["workflows"])
    assert [entry["target"] for entry in manifest["removals"]].count(relative.as_posix()) == 1


def test_retired_manual_conveyor_does_not_remain_dispatchable() -> None:
    assert not (ROOT / WORKFLOWS / "agents-73-codex-belt-conveyor-dispatch.yml").exists()
