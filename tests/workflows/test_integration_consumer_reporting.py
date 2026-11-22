"""Exercise Maint 62's authored issue routes with an inert GitHub client."""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[2] / ".github/workflows/maint-62-integration-consumer.yml"
)

REPLAY_REPORT = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const calls = [];
const existing = { title: 'Integration consumer failures', number: 4649 };
const rest = {
  issues: {
    getLabel: async () => {},
    listForRepo: async () => ({ data: input.existing ? [existing] : [] }),
    create: async ({ body }) => {
      calls.push(['open', body]);
      return { data: existing };
    },
    createComment: async ({ body }) => calls.push(['comment', body]),
    update: async ({ state }) => calls.push(['close', state]),
  },
};
const disabledRequire = (name) => {
  if (name === 'fs') return { existsSync: () => false };
  throw new Error('Unexpected import: ' + name);
};
const needs = {
  scenarios: { result: input.scenarios },
  'select-scenarios': { result: input.selection },
};
function condition(source, success, cancelled) {
  const expression = source.trim().slice(3, -2)
    .replaceAll('needs.select-scenarios.', "needs['select-scenarios'].");
  const evaluate = new Function('needs', 'success', 'cancelled', 'return (' + expression + ')');
  return evaluate(needs, () => success, () => cancelled);
}
async function replay() {
  const jobStarted = condition(input.jobCondition, true, input.reportState === 'cancel-before-job');
  for (const step of jobStarted ? input.steps : []) {
    const shouldRun = condition(step.condition, input.reportState !== 'setup-failed',
      input.reportState === 'cancel-before-write');
    if (shouldRun) {
      await new AsyncFunction('require', 'github', 'context', 'core', 'process', step.script)(
        disabledRequire, { rest }, { repo: { owner: 'stranske', repo: 'Workflows' } },
        { info: () => {} }, { env: { RUN_URL: input.runUrl } },
      );
    }
  }
  process.stdout.write(JSON.stringify({ jobStarted, calls }));
}
replay().catch(error => { console.error(error); process.exitCode = 1; });
"""


@pytest.mark.parametrize(
    ("selection", "scenarios", "existing", "report_state", "run_id", "expected"),
    [
        pytest.param("success", "cancelled", False, "ready", 43049069556, [], id="superseded-run"),
        pytest.param("cancelled", "skipped", True, "ready", 1, [], id="cancelled-selection"),
        pytest.param(
            "success", "success", True, "cancel-before-job", 1, [], id="cancelled-before-report"
        ),
        pytest.param("success", "failure", True, "setup-failed", 1, [], id="setup-failure"),
        pytest.param("success", "skipped", True, "ready", 1, [], id="no-selected-scenarios"),
        pytest.param("failure", "skipped", False, "ready", 1, ["open"], id="selection-failure"),
        pytest.param(
            "success", "failure", False, "ready", 38965200808, ["open"], id="scenario-failure"
        ),
        pytest.param(
            "success",
            "failure",
            True,
            "ready",
            38965200808,
            ["comment"],
            id="existing-failure-issue",
        ),
        pytest.param(
            "success", "success", True, "cancel-before-write", 1, [], id="cancelled-after-success"
        ),
        pytest.param(
            "success", "failure", False, "cancel-before-write", 1, [], id="cancelled-after-failure"
        ),
        pytest.param(
            "success",
            "success",
            True,
            "ready",
            43049167148,
            ["comment", "close"],
            id="real-success",
        ),
    ],
)
def test_integration_consumer_report_only_mutates_for_failure_or_success(
    selection, scenarios, existing, report_state, run_id, expected
):
    report = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["report"]
    run_url = f"https://github.com/stranske/Workflows/actions/runs/{run_id}"
    inputs = {
        "jobCondition": report["if"],
        "steps": [
            {"condition": step["if"], "script": step["with"]["script"]}
            for step in report["steps"]
            if "script" in step.get("with", {})
        ],
        "selection": selection,
        "scenarios": scenarios,
        "existing": existing,
        "reportState": report_state,
        "runUrl": run_url,
    }
    replay = subprocess.run(
        ["node", "-e", REPLAY_REPORT],
        input=json.dumps(inputs),
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    outcome = json.loads(replay.stdout)
    assert outcome["jobStarted"] == (report_state != "cancel-before-job")
    writes = outcome["calls"]
    assert [action for action, _ in writes] == expected
    for action, body in writes:
        if action == "close":
            assert body == "closed"
        else:
            assert run_url in body
