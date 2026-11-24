import json
import subprocess
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/agents-moderate-connector.yml"


def test_only_configured_connector_authors_reach_api_setup() -> None:
    job = yaml.safe_load(WORKFLOW.read_text())["jobs"]["moderate"]
    steps = job["steps"]
    names = [step["name"] for step in steps]
    author = next(step for step in steps if step.get("id") == "author")
    assert author["if"] == "steps.eligibility.outputs.should-run == 'true'"
    for name in ("Checkout retry helpers", "Setup API client", "Evaluate comment for moderation"):
        assert names.index(author["name"]) < names.index(name)
        assert steps[names.index(name)]["if"] == "steps.author.outputs.result == 'true'"
    assert job["outputs"]["moderated"] == "${{ steps.evaluate.outputs.delete || 'false' }}"

    # Run the authored github-script body with the same event and variable shapes.
    program = """
const { script, cases } = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const check = new Function('context', 'core', 'process', script);
const decisions = cases.map(([login, deny, allow]) => check(
  { payload: { issue: { number: 1 }, comment: { user: { login } } } },
  { info() {} },
  { env: { MODERATION_DENY_LIST: deny, MODERATION_ALLOW_LIST: allow } }
));
process.stdout.write(JSON.stringify(decisions));
"""
    cases = [
        ["stranske-keepalive[bot]", "", ""],
        ["chatgpt-codex-connector[bot]", "", ""],
        ["custom[bot]", " other, CUSTOM[bot] ", ""],
        ["custom[bot]", "custom[bot]", " CUSTOM[bot] "],
        ["chatgpt-codex-connector[bot]", ", ", ""],
        ["", "", ""],
    ]
    output = subprocess.check_output(
        ["node", "-e", program],
        input=json.dumps({"script": author["with"]["script"], "cases": cases}),
        text=True,
    )
    assert json.loads(output) == [False, True, True, False, False, False]
