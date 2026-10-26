"""Exercise dispatch-only PR metadata through the actual caller output script."""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = (ROOT / "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml",)


def assert_dispatch_base_ref(path: Path, base_ref: str) -> None:
    jobs = yaml.safe_load(path.read_text())["jobs"]
    evaluate = jobs["evaluate"]
    step = next(step for step in evaluate["steps"] if step.get("id") == "evaluate")
    # Run the production output script with authenticated evaluator metadata,
    # but no PR event payload or origin/HEAD to supply a fallback.
    harness = r"""
const fs = require('node:fs');
const assert = require('node:assert/strict');
const { script, baseRef } = JSON.parse(fs.readFileSync(0, 'utf8'));
const outputs = {};
const context = { eventName: 'workflow_dispatch', payload: {} };
const core = { setOutput: (key, value) => { outputs[key] = value; } };
process.env.INPUT_PR_NUMBER = '750';
process.env.INPUT_FORCE_RETRY = 'false';
const fixtureRequire = (name) => {
  assert.equal(name, './.github/scripts/keepalive_loop.js');
  return { evaluateKeepaliveLoop: async (options) => {
    assert.equal(options.overridePrNumber, 750);
    assert.equal(options.context.eventName, 'workflow_dispatch');
    return { prNumber: 750, prRef: 'repair/head', baseRef, action: 'conflict' };
  } };
};
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
new AsyncFunction('require', 'github', 'context', 'core', script)(
  fixtureRequire, {}, context, core
).then(() => process.stdout.write(JSON.stringify(outputs))).catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
"""
    result = subprocess.run(
        ["node", "-e", harness],
        input=json.dumps({"script": step["with"]["script"], "baseRef": base_ref}),
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    outputs = json.loads(result.stdout)
    assert outputs["pr_number"] == "750"
    assert outputs["pr_ref"] == "repair/head"
    assert outputs["base_ref"] == base_ref
    assert evaluate["outputs"]["base_ref"] == "${{ steps.evaluate.outputs.base_ref }}"
    caller = jobs["run-codex"]
    assert "evaluate" in caller["needs"]
    assert caller["with"]["base_ref"] == "${{ needs.evaluate.outputs.base_ref }}"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda path: path.name)
@pytest.mark.parametrize("base_ref", ["main", "release/2026.10", ""])
def test_dispatch_preserves_evaluated_pr_base(path: Path, base_ref: str) -> None:
    assert_dispatch_base_ref(path, base_ref)
