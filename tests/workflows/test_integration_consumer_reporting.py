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
async function replay() {
  for (const step of input.steps) {
    const expression = step.condition.trim().slice(3, -2)
      .replaceAll('needs.select-scenarios.', "needs['select-scenarios'].");
    if (new Function('needs', 'return (' + expression + ')')(needs)) {
      await new AsyncFunction('require', 'github', 'context', 'core', 'process', step.script)(
        disabledRequire, { rest }, { repo: { owner: 'stranske', repo: 'Workflows' } },
        { info: () => {} }, { env: { RUN_URL: input.runUrl } },
      );
    }
  }
  process.stdout.write(JSON.stringify(calls));
}
replay().catch(error => { console.error(error); process.exitCode = 1; });
"""


@pytest.mark.parametrize(
    ("selection", "scenarios", "existing", "run_id", "expected"),
    [
        pytest.param("success", "cancelled", False, 43049069556, [], id="superseded-run"),
        pytest.param("cancelled", "skipped", True, 1, [], id="cancelled-selection"),
        pytest.param("success", "skipped", True, 1, [], id="no-selected-scenarios"),
        pytest.param("failure", "skipped", False, 1, ["open"], id="selection-failure"),
        pytest.param("success", "failure", False, 38965200808, ["open"], id="scenario-failure"),
        pytest.param(
            "success", "failure", True, 38965200808, ["comment"], id="existing-failure-issue"
        ),
        pytest.param(
            "success", "success", True, 43049167148, ["comment", "close"], id="real-success"
        ),
    ],
)
def test_integration_consumer_report_only_mutates_for_failure_or_success(
    selection, scenarios, existing, run_id, expected
):
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["report"]["steps"]
    run_url = f"https://github.com/stranske/Workflows/actions/runs/{run_id}"
    inputs = {
        "steps": [
            {"condition": step["if"], "script": step["with"]["script"]}
            for step in steps
            if "script" in step.get("with", {})
        ],
        "selection": selection,
        "scenarios": scenarios,
        "existing": existing,
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
    writes = json.loads(replay.stdout)
    assert [action for action, _ in writes] == expected
    for action, body in writes:
        if action == "close":
            assert body == "closed"
        else:
            assert run_url in body
