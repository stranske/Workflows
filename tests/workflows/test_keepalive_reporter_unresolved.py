"""Execute the authored reporter resolver; an unresolved target must still report."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
REPORTERS = [
    Path(".github/workflows/agents-keepalive-loop-reporter.yml"),
    Path("templates/consumer-repo/.github/workflows/agents-keepalive-loop-reporter.yml"),
]
HARNESS = r"""
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const actual = require(process.cwd() + '/.github/scripts/keepalive_reporter_applicability.js');
const events = [];
const outputs = {};
let summary = '';
const core = {
  setOutput: (key, value) => { outputs[key] = value; },
  setFailed: (message) => events.push(['failed', message]),
  error: (message) => events.push(['error', message]),
  summary: {
    addHeading(value) { summary += value + '\n'; return this; },
    addRaw(value) { summary += value; return this; },
    async write() {
      if (input.summaryError) throw new Error('summary storage unavailable');
      events.push(['summary', summary]);
    },
  },
};
const run = {
  id: 12345, run_attempt: 2, head_sha: 'a'.repeat(40),
  conclusion: input.conclusion || 'failure', event: 'workflow_run', pull_requests: [],
};
if (input.associated) run.pull_requests = [{number: 42}];
const context = {
  eventName: input.manual ? 'workflow_dispatch' : 'workflow_run',
  repo: {owner: 'stranske', repo: 'example'},
  payload: {workflow_run: run, inputs: {pr_number: input.manual}},
};
const github = {rest: {actions: {getWorkflowRun: async () => {
  events.push(['read-origin']);
  return {data: {...run, ...(input.origin || {})}};
}}}};
const wrappedRequire = (name) => {
  if (name !== './.github/scripts/keepalive_reporter_applicability.js') throw Error(name);
  return {classifyReporterRun: (args) => {
    if (input.skip) return {status: 'skip'};
    return actual.classifyReporterRun({...args, lookupTarget: async () => {
      if (input.lookupError) throw Error(input.lookupError);
      return null;
    }});
  }};
};
const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
(async () => {
  await new AsyncFunction('require', 'github', 'context', 'core', input.script)(
    wrappedRequire, github, context, core,
  );
  console.log(JSON.stringify({events, outputs}));
})().catch(error => {console.error(error); process.exit(1);});
"""


def _resolve(path: Path, **scenario: object) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute the authored resolver")
    workflow = yaml.safe_load((ROOT / path).read_text())
    resolver = workflow["jobs"]["resolve-target"]
    script = next(
        step["with"]["script"] for step in resolver["steps"] if step.get("id") == "applicability"
    )
    result = subprocess.run(
        [node, "-e", HARNESS],
        input=json.dumps({"script": script, **scenario}),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out"])
def test_unassociated_workflow_run_reports_attributed_failure_before_failing(
    reporter: Path, conclusion: str
) -> None:
    result = _resolve(reporter, conclusion=conclusion)
    events = result["events"]
    assert [event[0] for event in events] == ["read-origin", "summary", "failed"]
    summary = events[1][1]
    assert "Repository: stranske/example" in summary
    assert "Upstream run: 12345" in summary
    assert "Attempt: 2" in summary
    assert f"Conclusion: {conclusion}" in summary
    assert "Head: " + "a" * 40 in summary
    assert "Unassociated run has no verified dispatch classification" in summary
    assert result["outputs"] == {
        "outcome": "unresolved",
        "skip": "false",
        "lock_pr_number": "",
        "pr_number": "",
        "ordinary_target": "false",
    }


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
def test_unavailable_lookup_reports_without_guessing_a_target(reporter: Path) -> None:
    result = _resolve(reporter, lookupError='index 503 <script> & "unsafe"')
    assert [event[0] for event in result["events"]] == ["summary", "failed"]
    summary = result["events"][0][1]
    assert "index 503 &lt;script&gt; &amp; &quot;unsafe&quot;" in summary
    assert "<script>" not in summary
    assert result["outputs"]["lock_pr_number"] == ""


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
def test_summary_write_failure_keeps_both_diagnostic_and_resolution_errors(
    reporter: Path,
) -> None:
    result = _resolve(reporter, summaryError=True)
    assert [event[0] for event in result["events"]] == ["read-origin", "error", "failed"]
    assert "summary storage unavailable" in result["events"][1][1]
    assert "no verified dispatch classification" in result["events"][2][1]
    assert result["outputs"]["outcome"] == "unresolved"


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
@pytest.mark.parametrize("scenario", [{"associated": True}, {"manual": "42"}])
def test_resolved_target_retains_pr_lock_without_unresolved_report(
    reporter: Path,
    scenario: dict,
) -> None:
    result = _resolve(reporter, **scenario)
    assert result["events"] == []
    assert result["outputs"]["outcome"] == "resolved"
    assert result["outputs"]["lock_pr_number"] == "42"
    assert result["outputs"]["skip"] == "false"


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
def test_no_report_needed_is_distinct_from_failed_resolution(reporter: Path) -> None:
    result = _resolve(reporter, skip=True)
    assert result["events"] == []
    assert result["outputs"]["outcome"] == "no-report-needed"
    assert result["outputs"]["skip"] == "true"


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
def test_invalid_manual_input_does_not_authorize_pr_mutation(reporter: Path) -> None:
    result = _resolve(reporter, manual="042")
    assert [event[0] for event in result["events"]] == ["summary", "failed"]
    assert result["outputs"]["outcome"] == "invalid-input"
    assert result["outputs"]["lock_pr_number"] == ""


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
def test_successful_and_skipped_upstream_runs_remain_outside_resolver(reporter: Path) -> None:
    workflow = yaml.safe_load((ROOT / reporter).read_text())
    condition = workflow["jobs"]["resolve-target"]["if"]
    assert "github.event.workflow_run.conclusion != 'success'" in condition
    assert "github.event.workflow_run.conclusion != 'skipped'" in condition
    report = workflow["jobs"]["report"]
    assert "needs.resolve-target.result == 'success'" in report["if"]
    assert "needs.resolve-target.outputs.lock_pr_number != ''" in report["if"]
