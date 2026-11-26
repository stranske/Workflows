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


def test_evaluate_skips_label_fetch_before_noise_deletion_path() -> None:
    job = yaml.safe_load(WORKFLOW.read_text())["jobs"]["moderate"]
    evaluate = next(step for step in job["steps"] if step.get("id") == "evaluate")
    script = evaluate["with"]["script"]
    program = r"""
const fs = require('fs');
const { script, cases } = JSON.parse(fs.readFileSync(0, 'utf8'));
const runner = new Function('github', 'context', 'core', `return (async () => {\n${script}\n})();`);
async function execute({ body, labels = [], fetchError = false }) {
  const output = {};
  const warnings = [];
  const core = {
    info() {},
    warning(message) { warnings.push(String(message)); },
    setOutput(name, value) { output[name] = String(value); },
  };
  let getCalls = 0;
  async function get() {
    getCalls++;
    if (fetchError) throw Object.assign(new Error('label fetch failed'), {status: 404});
    return { data: { labels } };
  }
  const github = { rest: { issues: { get } } };
  const comment = { body, id: 99, user: { login: 'chatgpt-codex-connector[bot]' } };
  const context = {
    payload: { comment, issue: { number: 5220 } },
    repo: { owner: 'stranske', repo: 'Workflows' },
  };
  process.env.MODERATION_DEBUG_LABEL = 'agents:debug';
  await runner(github, context, core);
  return { delete: output.delete ?? null, comment_id: output.comment_id ?? null,
    author: output.author ?? null, getCalls, warnings };
}
(async () => {
  const results = {};
  for (const [name, spec] of Object.entries(cases)) {
    results[name] = await execute(spec);
  }
  process.stdout.write(JSON.stringify(results));
})().catch((error) => { console.error(error); process.exit(1); });
"""
    noise = "To use Codex here you need to sign up."
    cases = {
        "substantive_noise": {"body": f"- [x] done\n{noise}"},
        "long_noise": {"body": " ".join(["word"] * 101) + f" {noise}"},
        "no_noise": {"body": "Legitimate connector status with no known noise phrase."},
        "genuine_noise": {"body": noise, "labels": []},
        "genuine_noise_debug": {"body": noise, "labels": [{"name": "agents:debug"}]},
        "read_failure": {"body": noise, "fetchError": True},
    }
    output = subprocess.check_output(
        ["node", "-e", program],
        input=json.dumps({"script": script, "cases": cases}),
        cwd=WORKFLOW.parents[2],
        text=True,
    )
    results = json.loads(output)

    for key in ("substantive_noise", "long_noise", "no_noise"):
        assert results[key]["getCalls"] == 0
        assert results[key]["delete"] == "false"

    genuine = results["genuine_noise"]
    assert genuine["getCalls"] == 1
    assert genuine["delete"] == "true"
    assert genuine["comment_id"] == "99"
    assert genuine["author"] == "chatgpt-codex-connector[bot]"

    debug = results["genuine_noise_debug"]
    assert debug["getCalls"] == 1
    assert debug["delete"] == "false"

    failed = results["read_failure"]
    assert failed["getCalls"] == 1
    assert failed["delete"] == "false"
    assert any("Moderation label scan failed" in note for note in failed["warnings"])
