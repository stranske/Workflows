"""Issue intake reads one non-agent label list and stops on hold labels.

Runs the shipped label scripts (consumer ``check_labels``, root ``bridge_preflight`` and the
reusable bridge's ``Resolve agent label``) under node with only the GitHub boundary faked, so
the tests exercise the real code and the real ``agent_registry.js``.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / ".github/scripts/agent_registry.js"
CONSUMER = ROOT / "templates/consumer-repo/.github/workflows/agents-issue-intake.yml"
ROOT_INTAKE = ROOT / ".github/workflows/agents-63-issue-intake.yml"
BRIDGE = ROOT / ".github/workflows/reusable-agents-issue-bridge.yml"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node is required for workflow scripts")

HOLDS = ["needs-human", "agents:paused", "agents:pause", "agents:auto-pilot-pause", "intake:held"]

HARNESS = r"""
const path = require('node:path');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const outputs = {};
const core = {
  summary: {addHeading() { return this; }, addTable() { return this; }, async write() {}},
  info() {}, warning() {}, notice() {}, error() {},
  setOutput: (key, value) => { outputs[key] = value; },
  setFailed: (message) => { outputs.__failed = message; },
  exportVariable: (key, value) => { process.env[key] = value; },
};
const labels = input.labels.map((name) => ({name}));
const github = {rest: {issues: {get: async () => ({data: {labels}})}}};
const context = {eventName: input.event, repo: {owner: 'stranske', repo: 'fixture'},
  payload: input.event === 'issues' ? {issue: {number: 7, labels}} : {}};
function localRequire(name) {
  if (name.endsWith('github-api-with-retry.js')) {
    return {withRetry: (fn) => fn(), createTokenAwareRetry: async () => ({github, withRetry: (fn) => fn()})};
  }
  if (name.endsWith('agent_registry.js')) return require(input.registry);
  if (name.startsWith('./')) return require(path.join(input.root, name));
  return require(name);
}
Object.assign(process.env, input.env);
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
new AsyncFunction('require', 'github', 'context', 'core', input.script)(localRequire, github, context, core)
  .then(() => console.log(JSON.stringify(outputs)))
  .catch((error) => { console.error(error); process.exit(1); });
"""


def _step_script(workflow: Path, job: str, *, step_id: str = "", step_name: str = "") -> str:
    steps = yaml.safe_load(workflow.read_text())["jobs"][job]["steps"]
    step = next(s for s in steps if (step_id and s.get("id") == step_id) or s.get("name") == step_name)
    return step["with"]["script"]


def _run(script: str, labels: list[str], *, env: dict | None = None, event: str = "issues") -> dict:
    script = (
        script.replace("${{ inputs.issue_number }}", "")
        .replace("${{ steps.ctx.outputs.issue }}", "7")
    )
    result = subprocess.run(
        [NODE, "-e", HARNESS],
        cwd=ROOT,
        input=json.dumps(
            {
                "script": script,
                "labels": labels,
                "event": event,
                "env": {"DEFAULT_AGENT": "codex", "INPUT_ISSUE": "7", "AGENT": "", **(env or {})},
                "registry": str(REGISTRY),
                "root": str(ROOT),
            }
        ),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    # The shipped scripts may log to stdout; the harness prints the outputs last.
    return json.loads(result.stdout.strip().splitlines()[-1])


def consumer_check(labels, **kwargs):
    return _run(_step_script(CONSUMER, "check_labels", step_id="check"), labels, **kwargs)


def root_preflight(labels, **kwargs):
    return _run(_step_script(ROOT_INTAKE, "bridge_preflight", step_id="inspect"), labels, **kwargs)


def bridge_resolve(labels, **kwargs):
    return _run(_step_script(BRIDGE, "bridge", step_id="agent_label"), labels, **kwargs)


@pytest.mark.parametrize("hold", HOLDS)
def test_held_issue_does_not_start_the_consumer_bridge(hold):
    assert consumer_check(["agent:codex"])["should_run"] == "true"
    assert consumer_check(["agent:codex", hold])["should_run"] == "false"


@pytest.mark.parametrize("hold", HOLDS)
def test_held_issue_does_not_start_the_root_bridge(hold):
    assert root_preflight(["agent:codex"]).get("held") is None
    held = root_preflight(["agent:codex", hold])
    assert held["held"] == "true"
    assert "__failed" not in held  # a hold is a skip, not a red run


def test_root_agent_bridge_job_honours_the_hold():
    condition = yaml.safe_load(ROOT_INTAKE.read_text())["jobs"]["agent_bridge"]["if"]
    assert "needs.bridge_preflight.outputs.held != 'true'" in condition


def test_lifting_the_hold_re_runs_intake():
    # Removing a hold fires `unlabeled`; both intakes listen for it, so the hold drains itself.
    for workflow in (CONSUMER, ROOT_INTAKE):
        on = yaml.safe_load(workflow.read_text())
        on = on.get("on") or on[True]
        assert "unlabeled" in on["issues"]["types"]


def test_agent_auto_beside_a_concrete_agent_passes_check_labels():
    consumer = consumer_check(["agent:auto", "agent:codex"])
    assert (consumer["should_run"], consumer["agent"]) == ("true", "codex")
    preflight = root_preflight(["agent:auto", "agent:codex"])
    assert "__failed" not in preflight
    assert preflight["agent_key"] == "codex"
    bridge = bridge_resolve(["agent:auto", "agent:codex"])
    assert "__failed" not in bridge
    assert bridge["agent"] == "codex"


def test_agent_auto_alone_takes_the_chosen_agent():
    consumer = consumer_check(["agent:auto"], env={"DEFAULT_AGENT": "cursor"})
    assert (consumer["should_run"], consumer["agent"]) == ("true", "cursor")
    assert root_preflight(["agent:auto"], env={"DEFAULT_AGENT": "cursor"})["agent_key"] == "cursor"
    assert bridge_resolve(["agent:auto"], env={"AGENT": "cursor"})["agent"] == "cursor"


@pytest.mark.parametrize(
    "labels, agent",
    [
        (["agents:formatted", "agent:cursor"], "cursor"),
        (["agents:keepalive", "agent:codex"], "codex"),
        (["agent:needs-attention", "agent:muse"], "muse"),
    ],
)
def test_control_labels_never_become_the_agent(labels, agent):
    assert consumer_check(labels)["agent"] == agent
    assert root_preflight(labels)["agent_key"] == agent
    assert bridge_resolve(labels)["agent"] == agent


def test_control_label_alone_does_not_start_the_bridge():
    assert consumer_check(["agents:formatted"])["should_run"] == "false"
    assert "__failed" in root_preflight(["agents:formatted"])


def test_one_definition_of_the_non_agent_label_list():
    """The intake/bridge scripts read agent_registry.js instead of holding their own copy."""
    for workflow in (CONSUMER, ROOT_INTAKE, BRIDGE):
        text = workflow.read_text()
        assert "'apply-suggestions'" not in text, workflow
        assert '"apply-suggestions"' not in text, workflow
    registry = REGISTRY.read_text()
    assert registry.count("'apply-suggestions'") == 1
    template = ROOT / "templates/consumer-repo/.github/scripts/agent_registry.js"
    assert template.read_bytes() == REGISTRY.read_bytes()


@pytest.mark.parametrize(
    "workflow, job, step",
    [
        (BRIDGE, "bridge", "Checkout Workflows agent registry"),
        (ROOT_INTAKE, "chatgpt_sync", "Checkout Workflows agent registry"),
    ],
)
def test_workflows_called_at_main_read_the_workflows_registry(workflow, job, step):
    # Consumers call these at @main; their synced agent_registry.js can lag the new export.
    steps = yaml.safe_load(workflow.read_text())["jobs"][job]["steps"]
    checkout = next(s for s in steps if s.get("name") == step)
    assert checkout["with"]["repository"] == "stranske/Workflows"
    assert ".github/scripts/agent_registry.js" in checkout["with"]["sparse-checkout"]
