"""Every registry agent marked belt-capable must have everything a belt run needs (Workflows#3929).

The belt workflows are registry-driven and never run the agent themselves; the round runs in the
keepalive loop's static `run-<agent>` job once the belt PR carries `agent:<agent>`.
"""

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


def test_belt_rotation_uses_real_credential_availability(tmp_path):
    """Run the actual workflow function with the real decision module and API stubs."""
    import json
    import subprocess

    workflow = yaml.safe_load((ROOT / ".github/workflows/agents-auto-pilot.yml").read_text())
    step = next(
        s for s in workflow["jobs"]["auto-pilot"]["steps"] if s.get("id") == "create_pr_step"
    )
    assert step["env"]["HAS_CURSOR_API_KEY"] == "${{ secrets.CURSOR_API_KEY != '' }}"
    script = step["with"]["script"]
    function = script[
        script.index("async function tryBeltStallRotation") : script.index(
            "// Check if branch exists"
        )
    ]
    harness = r"""
const vm = require('node:vm');
const assert = require('node:assert/strict');
const rotation = require(process.argv[2]);
const config = JSON.parse(process.argv[3]);
const code = JSON.parse(process.argv[4]);
async function run(names, flags, unavailable = false) {
  const dispatches = [];
  const client = {rest: {
    issues: {get: async () => ({data: {labels: ['agent:claude', 'agents:tried-codex']}}),
      removeLabel: async () => ({}), getLabel: async () => ({}), addLabels: async () => ({}),
      createComment: async () => ({})},
    repos: {get: async () => ({data: {default_branch: 'main'}})},
    actions: {listRepoSecrets: () => {}, createWorkflowDispatch: async x => dispatches.push(x)}},
    paginate: async () => {if (unavailable) throw Error('forbidden'); return names.map(name => ({name}));}};
  const context = {require: name => name.includes('agent_stall_rotation') ? rotation : {loadAgentRegistry: () => config},
    process: {env: flags}, context: {repo: {owner: 'test', repo: 'fixture'}},
    withRetry: fn => fn(client), core: {info: () => {}, warning: () => {}}, stepCount: 5};
  const rotated = await vm.runInNewContext('(async () => {' + code + '; return tryBeltStallRotation({issueNumber: 9, stallCount: 5, warnMsg: "test"});})()', context);
  return {rotated, dispatches};
}
(async () => {
  assert.equal((await run([], {})).rotated, false);
  const present = await run(['CURSOR_API_KEY'], {});
  assert.equal(present.rotated, true);
  assert.equal(present.dispatches[0].inputs.agent_key, 'cursor');
  assert.equal((await run([], {}, true)).rotated, false);
  assert.equal((await run([], {HAS_CURSOR_API_KEY: 'true'}, true)).rotated, true);
})().catch(error => {console.error(error); process.exit(1);});
"""
    fixture = tmp_path / "belt-credentials.cjs"
    fixture.write_text(harness)
    config = yaml.safe_load(REGISTRIES[0].read_text())
    result = subprocess.run(
        [
            "node",
            str(fixture),
            str(ROOT / ".github/scripts/agent_stall_rotation.js"),
            json.dumps(config),
            json.dumps(function),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
