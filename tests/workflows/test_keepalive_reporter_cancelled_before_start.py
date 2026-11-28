"""Execute the authored reporter step: a cancelled-before-start origin is not a failure.

Cohesion review B1 (2026-11-28). Burst label events cancel pending ``agents-81`` runs before any
job exists; the reporter then failed with "Originating worker execution evidence is unknown"
(19 of 60 reporter runs in Manager-Database). The step now treats exactly one unknown as not
applicable -- the exact attempt is completed/cancelled AND its jobs listing is empty -- and keeps
failing closed for every other unknown.
"""

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
GUARD = "if (startEvidence === 'cancelled-before-start') {"
HARNESS = r"""
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const evidence = require(process.cwd() + '/' + input.helper);
const events = [];
let summary = '';
const core = {
  info: () => {},
  warning: (message) => events.push(['warning', message]),
  notice: (message) => events.push(['notice', message]),
  setFailed: (message) => events.push(['failed', message]),
  summary: {
    addHeading(value) { summary += value + '\n'; return this; },
    addRaw(value) { summary += value; return this; },
    async write() { events.push(['summary', summary]); },
  },
};
const headSha = 'a'.repeat(40);
const run = {
  id: 46087668529, run_attempt: 1, head_sha: headSha, conclusion: input.conclusion,
  event: 'workflow_run', pull_requests: [{number: 42}], html_url: 'https://example.invalid/run',
};
const context = {
  eventName: 'workflow_run',
  repo: {owner: 'stranske', repo: 'Manager-Database'},
  payload: {workflow_run: run},
};
const registryYaml = 'version: 1\ndefault_agent: codex\nagents:\n  codex:\n' +
  '    capabilities:\n      pr_keepalive: true\n';
const notFound = () => Object.assign(new Error('Not Found'), {status: 404});
const github = {
  request: async (route) => {
    events.push(['read-attempt']);
    if (input.attemptError) throw notFound();
    return {data: {id: run.id, run_attempt: 1, head_sha: headSha, status: 'completed',
      conclusion: input.conclusion, ...(input.attempt || {})}};
  },
  paginate: async () => input.jobs,
  rest: {
    actions: {listJobsForWorkflowRunAttempt: () => {}},
    repos: {getContent: async () => ({data: {type: 'file', encoding: 'base64',
      content: Buffer.from(registryYaml).toString('base64')}})},
  },
};
const wrappedRequire = (name) => {
  if (name === './.github/scripts/keepalive_worker_evidence.js') return evidence;
  if (name === './.github/scripts/keepalive_reporter_applicability.js') {
    return {
      replayReporterAuthority: async () => ({results: []}),
      recoverReporterAuthority: async () => {
        events.push(['recover']);
        return {status: 'superseded', prNumber: 42};
      },
    };
  }
  if (name === './.github/scripts/keepalive_state.js') {
    return {loadKeepaliveState: async () => ({state: {running: false}})};
  }
  if (name === './.github/scripts/keepalive_loop.js') {
    return {updateKeepaliveLoopSummary: async () => events.push(['update-summary'])};
  }
  throw new Error('unexpected require ' + name);
};
const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
(async () => {
  await new AsyncFunction('require', 'github', 'context', 'core', input.script)(
    wrappedRequire, github, context, core,
  );
  console.log(JSON.stringify({events}));
})().catch(error => {console.error(error); process.exit(1);});
"""


def _step_script(path: Path) -> str:
    workflow = yaml.safe_load((ROOT / path).read_text())
    steps = workflow["jobs"]["report"]["steps"]
    return next(step["with"]["script"] for step in steps if step.get("id") == "update-summary")


def _run(path: Path, **scenario: object) -> list:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute the authored reporter step")
    helper = str(path.parent.parent / "scripts/keepalive_worker_evidence.js")
    result = subprocess.run(
        [node, "-e", HARNESS],
        input=json.dumps({"script": _step_script(path), "helper": helper, **scenario}),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)["events"]


def _kinds(events: list) -> list:
    return [event[0] for event in events]


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
def test_cancelled_before_any_job_is_not_applicable(reporter: Path) -> None:
    events = _run(reporter, conclusion="cancelled", jobs=[])
    assert _kinds(events) == ["read-attempt", "notice", "summary"]
    assert "cancelled before any job started (0 jobs)" in events[1][1]
    assert "46087668529" in events[1][1]
    assert "not applicable" in events[2][1]


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
@pytest.mark.parametrize(
    "scenario",
    [
        # A real failure with no recognisable worker job is still unknown.
        {"conclusion": "failure", "jobs": []},
        # Cancelled after a job existed: something may have run.
        {
            "conclusion": "cancelled",
            "jobs": [{"name": "Evaluate", "status": "completed", "conclusion": "cancelled"}],
        },
        # The attempt API disagrees with the payload.
        {"conclusion": "cancelled", "jobs": [], "attempt": {"conclusion": "failure"}},
        {"conclusion": "cancelled", "jobs": [], "attempt": {"head_sha": "c" * 40}},
        # The proof cannot be read.
        {"conclusion": "cancelled", "jobs": [], "attemptError": True},
    ],
    ids=["failed", "cancelled-with-job", "attempt-not-cancelled", "sha-mismatch", "attempt-404"],
)
def test_every_other_unknown_still_fails_closed(reporter: Path, scenario: dict) -> None:
    events = _run(reporter, **scenario)
    assert _kinds(events)[-1] == "failed"
    assert "Originating worker execution evidence is unknown" in events[-1][1]
    assert "notice" not in _kinds(events)
    assert "recover" not in _kinds(events)


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
def test_known_worker_evidence_still_reconciles(reporter: Path) -> None:
    jobs = [
        {
            "name": "Keepalive next task (Codex)",
            "status": "completed",
            "conclusion": "skipped",
        }
    ]
    events = _run(reporter, conclusion="cancelled", jobs=jobs)
    assert _kinds(events) == ["recover"]


@pytest.mark.parametrize("reporter", REPORTERS, ids=["root", "consumer"])
def test_deliberate_break_removing_the_guard_is_detected(
    reporter: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the guard the cancelled-before-start run goes red again; the test must see it."""
    original = _step_script(reporter)
    assert original.count(GUARD) == 1
    broken = original.replace(GUARD, "if (false) {", 1)
    with monkeypatch.context() as mutation:
        mutation.setattr(
            __name__ + "._step_script",
            lambda path: broken if path == reporter else original,
        )
        with pytest.raises(AssertionError) as failure:
            test_cancelled_before_any_job_is_not_applicable(reporter)
        assert "failed" in str(failure.value)
    assert _step_script(reporter) == original
    test_cancelled_before_any_job_is_not_applicable(reporter)
