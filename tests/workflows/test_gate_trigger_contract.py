"""Prevent label churn from restarting Gate while commits still supersede runs."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
GATE_FILES = (
    ".github/workflows/pr-00-gate.yml",
    "templates/consumer-repo/.github/workflows/pr-00-gate.yml",
)


@pytest.mark.parametrize("workflow_path", GATE_FILES)
def test_gate_trigger_contract(workflow_path: str) -> None:
    workflow = yaml.safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    # PyYAML's YAML 1.1 resolver reads the Actions key `on` as boolean True.
    triggers = workflow.get("on", workflow.get(True))
    types = triggers["pull_request"]["types"]

    assert "labeled" not in types, f"{workflow_path}: labels must not restart Gate"
    assert "opened" in types, f"{workflow_path}: new PRs must start Gate"
    assert "synchronize" in types, f"{workflow_path}: new commits must start Gate"
    assert workflow["concurrency"]["cancel-in-progress"] == (
        "${{ github.event_name != 'workflow_dispatch' }}"
    ), f"{workflow_path}: new commits must still supersede in-flight runs"


def test_gate_triggers_match_template() -> None:
    workflows = [yaml.safe_load((ROOT / path).read_text(encoding="utf-8")) for path in GATE_FILES]
    triggers = [workflow.get("on", workflow.get(True)) for workflow in workflows]
    assert triggers[0] == triggers[1], f"Gate triggers must agree across {GATE_FILES}"


@pytest.mark.parametrize("workflow_path", GATE_FILES)
def test_dispatch_retains_pr_context_and_queues(workflow_path: str) -> None:
    workflow = yaml.safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["workflow_dispatch"]["inputs"]["pr_number"]["type"] == "string"
    assert "inputs.pr_number" in workflow["concurrency"]["group"]
    assert workflow["concurrency"]["cancel-in-progress"] == (
        "${{ github.event_name != 'workflow_dispatch' }}"
    )
    for name in ("issue-consistency", "test-quality"):
        assert (
            "fromJSON(needs.resolve-pr.outputs.pull_request).number"
            in (workflow["jobs"][name]["if"])
        ), f"{workflow_path}: {name} must run for PR dispatches too"
    for name, job in workflow["jobs"].items():
        if name == "resolve-pr":
            continue
        assert "resolve-pr" in job["needs"], f"{workflow_path}: {name} needs resolved PR"
        if "steps" in job:
            assert job["env"]["GATE_PR_JSON"] == "${{ needs.resolve-pr.outputs.pull_request }}"
            assert job["steps"][0]["name"] == "Restore resolved PR event for Gate helpers"


@pytest.mark.parametrize("workflow_path", GATE_FILES)
def test_dispatch_resolves_current_head_and_rejects_races(workflow_path: str) -> None:
    """Execute the actual workflow resolver against API fixtures, not a copy."""
    import json
    import subprocess

    workflow = yaml.safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    script = workflow["jobs"]["resolve-pr"]["steps"][0]["with"]["script"]
    harness = r"""
const assert = require('node:assert/strict');
const execute = new (Object.getPrototypeOf(async function(){}).constructor)(
  'github', 'context', 'core', SCRIPT);
(async () => {
  process.env.PR_NUMBER = '42';
  process.env.GITHUB_REPOSITORY = 'owner/repo';
  const pr = {number: 42, state: 'open', body: 'sealed body',
    head: {sha: 'current-head', repo: {full_name: 'owner/repo'}}};
  const context = {eventName: 'workflow_dispatch', sha: 'current-head',
    payload: {}, repo: {owner: 'owner', repo: 'repo'}};
  const github = {rest: {pulls: {get: async args => {
    assert.equal(args.pull_number, 42); return {data: pr};
  }}}};
  let output;
  const core = {setOutput: (name, value) => {output = JSON.parse(value);}};
  await execute(github, context, core);
  assert.deepEqual(output, pr);
  for (const change of [
    p => {p.head.sha = 'new-head';},
    p => {p.head.repo.full_name = 'fork/repo';},
    p => {p.state = 'closed';},
  ]) {
    const original = structuredClone(pr); change(pr);
    await assert.rejects(execute(github, context, core), /current open same-repository/);
    Object.assign(pr, original);
  }
  process.env.PR_NUMBER = 'oops';
  await assert.rejects(execute(github, context, core), /positive integer/);
  context.eventName = 'pull_request'; context.payload.pull_request = pr;
  await execute(github, context, core);
  assert.deepEqual(output, pr);
  context.eventName = 'workflow_dispatch'; context.payload = {};
  process.env.PR_NUMBER = '';
  await execute(github, context, core);
  assert.equal(output, null);
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    result = subprocess.run(
        ["node", "-e", "const SCRIPT = " + json.dumps(script) + ";\n" + harness],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("workflow_path", GATE_FILES)
def test_dispatch_restores_event_for_seal_and_summary(workflow_path: str, tmp_path: Path) -> None:
    import json
    import subprocess

    workflow = yaml.safe_load((ROOT / workflow_path).read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    script = jobs["generated-delivery-seal"]["steps"][0]["with"]["script"]
    assert script == jobs["summary"]["steps"][0]["with"]["script"]
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"inputs": {"pr_number": "42"}}))
    pr = {"number": 42, "body": "fresh sealed body", "head": {"sha": "current-head"}}
    harness = (
        "process.env.GITHUB_EVENT_PATH = " + json.dumps(str(event_path)) + ";\n"
        "process.env.GATE_PR_JSON = " + json.dumps(json.dumps(pr)) + ";\n" + script
    )
    subprocess.run(["node", "-e", harness], check=True, capture_output=True, text=True)
    event = json.loads(event_path.read_text())
    assert event["pull_request"] == pr
    assert event["number"] == 42
    assert event["inputs"] == {"pr_number": "42"}
