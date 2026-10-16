"""Every registry agent marked belt-capable must have everything a belt run needs (Workflows#3929).

The belt workflows are registry-driven and never run the agent themselves; the round runs in the
keepalive loop's static `run-<agent>` job once the belt PR carries `agent:<agent>`.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRIES = (
    ROOT / ".github/agents/registry.yml",
    ROOT / "templates/consumer-repo/.github/agents/registry.yml",
)
KEEPALIVE_SURFACES = (
    ROOT / ".github/workflows/agents-keepalive-loop.yml",
    ROOT / "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml",
)


def _belt_agents(registry: Path) -> dict:
    agents = yaml.safe_load(registry.read_text())["agents"]
    return {k: v for k, v in agents.items() if (v.get("capabilities") or {}).get("belt") is True}


def _problems(agent: str, config: dict) -> list[str]:
    problems = []
    runner = config.get("runner_workflow") or ""
    if not (ROOT / runner).is_file():
        problems.append(f"{agent}: runner_workflow {runner!r} does not exist")
    if not str(config.get("branch_prefix") or "").endswith("/issue-"):
        problems.append(f"{agent}: branch_prefix must end with '/issue-'")
    labels = (ROOT / ".github/labels-core.yml").read_text()
    if f"name: agent:{agent}" not in labels:
        problems.append(f"{agent}: label agent:{agent} is not in labels-core.yml")
    for surface in KEEPALIVE_SURFACES:
        jobs = yaml.safe_load(surface.read_text())["jobs"]
        if f"run-{agent}" not in jobs:
            problems.append(f"{agent}: no run-{agent} job in {surface.name}")
    return problems


def test_every_belt_capable_agent_has_a_worker_path():
    for registry in REGISTRIES:
        belt = _belt_agents(registry)
        assert {"codex", "claude", "cursor"} <= set(belt), (registry.name, sorted(belt))
        problems = [p for agent, cfg in belt.items() for p in _problems(agent, cfg)]
        assert not problems, problems


def test_agent_without_a_worker_path_is_rejected():
    fake = {"runner_workflow": ".github/workflows/reusable-nope-run.yml", "branch_prefix": "nope"}
    assert len(_problems("nope", fake)) == 5


def test_belt_workflows_stay_registry_driven():
    for name in (
        "agents-71-codex-belt-dispatcher.yml",
        "agents-72-codex-belt-worker.yml",
        "agents-73-codex-belt-conveyor.yml",
    ):
        assert "agent_registry.js" in (ROOT / ".github/workflows" / name).read_text(), name
