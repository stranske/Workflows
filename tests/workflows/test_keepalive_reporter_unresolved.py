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
const actual = require(process.cwd() + '/' + input.helper);
const events = [];
const outputs = {};
let summary = '';
const core = {
  setOutput: (key, value) => { outputs[key] = value; },
  setFailed: (message) => events.push(['failed', message, {...outputs}]),
  error: (message) => events.push(['error', message]),
  notice: (message) => events.push(['notice', message]),
  summary: {
    addHeading(value) { summary += value + '\n'; return this; },
    addRaw(value) { summary += value; return this; },
    async write() {
      if (input.summaryError) throw new Error('summary storage unavailable');
      events.push(['summary', summary, {...outputs}]);
    },
  },
};
const run = {
  id: 12345, run_attempt: 2, head_sha: 'a'.repeat(40),
  conclusion: input.conclusion || 'failure', event: 'workflow_run', pull_requests: [],
};
if (input.associated) run.pull_requests = [{number: 42}];
const context = {
  eventName: Object.hasOwn(input, 'manual') ? 'workflow_dispatch' : 'workflow_run',
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
      return input.indexedTarget || null;
    }});
  }};
};
const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
(async () => {
  await new AsyncFunction('require', 'github', 'context', 'core', input.script)(
    wrappedRequire, github, context, core,
  );
  console.log(JSON.stringify({events, outputs, helper: input.helper}));
})().catch(error => {console.error(error); process.exit(1);});
"""


def _helper_for(reporter: Path) -> str:
    """Classifier path checked out beside the reporter workflow under test."""
    return str(reporter.parent.parent / "scripts/keepalive_reporter_applicability.js")


def _resolve(path: Path, **scenario: object) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute the authored resolver")
    workflow = yaml.safe_load((ROOT / path).read_text())
    resolver = workflow["jobs"]["resolve-target"]
    script = next(
        step["with"]["script"] for step in resolver["steps"] if step.get("id") == "applicability"
    )
    helper = _helper_for(path)
    result = subprocess.run(
        [node, "-e", HARNESS],
        input=json.dumps(
            {
                "script": script,
                "helper": helper,
                **scenario,
            }
        ),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    # Consumer scenarios must not silently bind the root classifier copy.
    assert payload["helper"] == helper
    return payload


def test_root_and_consumer_classifier_paths_are_distinct() -> None:
    root_helper, consumer_helper = (_helper_for(path) for path in REPORTERS)
    assert root_helper != consumer_helper
    assert (ROOT / root_helper).is_file()
    assert (ROOT / consumer_helper).is_file()


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
def test_resolver_binds_classifier_from_reporter_tree(reporter: Path) -> None:
    """Root and consumer scenarios must load their own checked-out classifier."""
    helper = _helper_for(reporter)
    assert (ROOT / helper).is_file()
    result = _resolve(reporter, conclusion="failure")
    assert result["helper"] == helper
    if reporter.parts[0] == "templates":
        assert helper.startswith("templates/consumer-repo/.github/scripts/")
    else:
        assert helper == ".github/scripts/keepalive_reporter_applicability.js"


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out"])
def test_unassociated_workflow_run_reports_attributed_failure_before_failing(
    reporter: Path, conclusion: str
) -> None:
    """Failed unassociated runs publish full attribution before visible failure."""
    result = _resolve(reporter, conclusion=conclusion)
    assert [event[0] for event in result["events"]] == ["read-origin", "summary", "failed"]
    summary = result["events"][1][1]
    for value in (
        "Repository: stranske/example",
        "Upstream run: 12345",
        "Attempt: 2",
        f"Conclusion: {conclusion}",
        "Event: workflow_run",
        "Head: " + "a" * 40,
        "Reporter outcome: unresolved",
        "unassociated run has no verified dispatch classification",
        "No PR state was changed. Recover the verified target, then retry the reporter.",
    ):
        assert value in summary
    assert result["events"][2][0] == "failed"
    assert "Reporter applicability unavailable:" in result["events"][2][1]
    assert result["outputs"] == {
        "outcome": "unresolved",
        "skip": "false",
        "lock_pr_number": "",
        "pr_number": "",
        "ordinary_target": "false",
    }
    # Empty lock forbids the mutating report job; diagnostic is not reconciliation.
    assert result["events"][1][2]["lock_pr_number"] == ""
    assert result["events"][2][2]["lock_pr_number"] == ""


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
    result = _resolve(reporter, summaryError=True, lookupError="index unavailable")
    assert [event[0] for event in result["events"]] == ["error", "failed"]
    assert "summary storage unavailable" in result["events"][0][1]
    assert "index unavailable" in result["events"][1][1]
    assert (
        result["events"][1][2]
        == result["outputs"]
        == {
            "outcome": "unresolved",
            "skip": "false",
            "lock_pr_number": "",
            "pr_number": "",
            "ordinary_target": "false",
        }
    )


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
@pytest.mark.parametrize(
    "scenario",
    [{"associated": True}, {"manual": "42"}, {"indexedTarget": {"prNumber": 42}}],
    ids=["associated", "manual", "immutable-index"],
)
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
    assert [event[0] for event in result["events"]] == ["notice", "summary"]
    assert result["outputs"]["outcome"] == "no-report-needed"
    assert result["outputs"]["skip"] == "true"


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
@pytest.mark.parametrize("manual", ["042", "", None, "0", "-1", "1.5", "42 ", "9007199254740992"])
def test_invalid_manual_input_does_not_authorize_pr_mutation(
    reporter: Path, manual: str | None
) -> None:
    result = _resolve(reporter, manual=manual)
    assert [event[0] for event in result["events"]] == ["summary", "failed"]
    assert "Authority replay requires a canonical positive PR number" in result["events"][0][1]
    assert (
        result["events"][0][2]
        == result["events"][1][2]
        == result["outputs"]
        == {
            "outcome": "invalid-input",
            "skip": "false",
            "lock_pr_number": "",
            "pr_number": "",
            "ordinary_target": "false",
        }
    )


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
@pytest.mark.parametrize("pr_number", [0, -1, 1.5, "invalid", "9007199254740992"])
def test_invalid_indexed_target_reports_without_granting_a_pr_lock(
    reporter: Path, pr_number: int | float | str
) -> None:
    result = _resolve(reporter, indexedTarget={"prNumber": pr_number})
    assert [event[0] for event in result["events"]] == ["summary", "failed"]
    assert "Reporter target did not resolve to a positive PR number" in result["events"][0][1]
    assert (
        result["events"][0][2]
        == result["events"][1][2]
        == result["outputs"]
        == {
            "outcome": "unresolved",
            "skip": "false",
            "lock_pr_number": "",
            "pr_number": "",
            "ordinary_target": "false",
        }
    )


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
@pytest.mark.parametrize(
    "mismatch",
    [
        {"id": 99999},
        {"run_attempt": 3},
        {"head_sha": "b" * 40},
        {"event": "workflow_run"},
        {"path": ".github/workflows/unverified-producer.yml"},
    ],
    ids=["run", "attempt", "head", "event", "producer"],
)
def test_unverified_origin_title_cannot_authorize_a_pr_lock(reporter: Path, mismatch: dict) -> None:
    origin = {
        "event": "workflow_dispatch",
        "path": ".github/workflows/agents-keepalive-loop.yml",
        "display_title": "keepalive-dispatch/v2 ordinary pr=42",
        **mismatch,
    }
    result = _resolve(reporter, origin=origin)
    assert [event[0] for event in result["events"]] == ["read-origin", "summary", "failed"]
    assert "unassociated run has no verified dispatch classification" in result["events"][1][1]
    assert result["outputs"] == {
        "outcome": "unresolved",
        "skip": "false",
        "lock_pr_number": "",
        "pr_number": "",
        "ordinary_target": "false",
    }


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
def test_successful_and_skipped_upstream_runs_remain_outside_resolver(reporter: Path) -> None:
    workflow = yaml.safe_load((ROOT / reporter).read_text())
    condition = workflow["jobs"]["resolve-target"]["if"]
    assert "github.event.workflow_run.conclusion != 'success'" in condition
    assert "github.event.workflow_run.conclusion != 'skipped'" in condition
    report = workflow["jobs"]["report"]
    assert "needs.resolve-target.result == 'success'" in report["if"]
    assert "needs.resolve-target.outputs.lock_pr_number != ''" in report["if"]
