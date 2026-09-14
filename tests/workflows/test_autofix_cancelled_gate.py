"""Execute the actual workflow evaluators against recorded-style GitHub responses."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = [
    ".github/workflows/agents-autofix-loop.yml",
    "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml",
]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node is required for workflow scripts")


@pytest.mark.parametrize(
    "workflow",
    [
        ".github/workflows/autofix.yml",
        "templates/consumer-repo/.github/workflows/autofix.yml",
    ],
)
@pytest.mark.parametrize("evidence", ["check", "job"])
@pytest.mark.parametrize("name", ["lint-format", "lint-ruff", "pytest"])
@pytest.mark.parametrize(
    "conclusion", ["timed_out", "failure", "cancelled", "skipped", "success", "neutral"]
)
def test_autofix_lint_failure_eligibility(workflow, tmp_path, evidence, name, conclusion):
    """Run each shipped context evaluator with isolated check or job evidence."""
    document = yaml.safe_load((ROOT / workflow).read_text())
    script = next(
        step["with"]["script"]
        for job in document["jobs"].values()
        for step in job.get("steps", [])
        if step.get("id") == "context"
    )
    fixture = {"evidence": evidence, "name": name, "conclusion": conclusion}
    # Load the production step as ordinary JavaScript, mocking only API boundaries.
    harness = r"""
import assert from 'node:assert/strict';
const fixture = JSON.parse(process.env.FIXTURE);
const output = {};
const calls = [];
const core = {setOutput: (key, value) => output[key] = value,
  info: () => {}, warning: () => {}, setFailed: (message) => {throw Error(message);}};
const context = {eventName: 'workflow_run', actor: 'fixture',
  repo: {owner: 'stranske', repo: 'fixture'}, payload: {workflow_run: {
    id: 100, name: 'Gate', conclusion: 'timed_out', head_sha: 'current-head',
    pull_requests: [{number: 7}]
  }}};
const result = {name: fixture.name, conclusion: fixture.conclusion};
const github = {rest: {
  actions: {listJobsForWorkflowRun: async (params) => {
    assert.equal(params.run_id, 100);
    calls.push('jobs');
    return fixture.evidence === 'job' ? [result] : [];
  }},
  checks: {listForRef: async (params) => {
    assert.equal(params.ref, 'current-head');
    calls.push('checks');
    return {data: {check_runs: fixture.evidence === 'check' ? [result] : []}};
  }},
  pulls: {
    get: async (params) => {
      assert.equal(params.pull_number, 7);
      return {data: {number: 7, state: 'open', draft: false, labels: [],
        head: {sha: 'current-head', ref: 'fix-lint', repo: {full_name: 'stranske/fixture'}},
        base: {repo: {full_name: 'stranske/fixture'}}}};
    },
    listFiles: async () => [{filename: 'src/example.py'}]
  }
}};
const require = (name) => {
  assert.equal(name, './.github/scripts/github-api-with-retry.js');
  return {createTokenAwareRetry: async () => ({
    withRetry: (fn) => fn(github),
    paginateWithRetry: (method, params) => method(params)
  })};
};
async function evaluate() {
"""
    runner = tmp_path / "autofix-context.mjs"
    runner.write_text(
        harness + script + "\n}\nawait evaluate();\nconsole.log(JSON.stringify({output, calls}));\n"
    )
    completed = subprocess.run(
        [NODE, str(runner)],
        cwd=tmp_path,
        env={**os.environ, "FIXTURE": json.dumps(fixture)},
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)
    eligible = name in {"lint-format", "lint-ruff"} and conclusion in {"failure", "timed_out"}
    assert result["output"]["should_run"] == str(eligible).lower()
    assert result["calls"] == (["jobs"] if evidence == "job" and eligible else ["jobs", "checks"])
    if eligible:
        assert result["output"]["pr_number"] == 7
        assert result["output"]["head_sha"] == "current-head"


def execute(
    workflow,
    tmp_path,
    conclusion="failure",
    history=(),
    jobs=None,
    historical_jobs=None,
    *,
    run_attempt=1,
    attempt_jobs=None,
    pr_labels=None,
    pr_body="",
):
    document = yaml.safe_load((ROOT / workflow).read_text())
    steps = document["jobs"]["prepare"]["steps"]
    script = next(s["with"]["script"] for s in steps if s.get("id") == "evaluate")
    escalation = next(
        s["with"]["script"]
        for job in document["jobs"].values()
        for s in job.get("steps", [])
        if "Autofix attempts exhausted" in s.get("with", {}).get("script", "")
    )
    run = {
        "id": 100,
        "workflow_id": 42,
        "head_sha": "current-head",
        "conclusion": conclusion,
        "event": "pull_request",
        "pull_requests": [{"number": 7}],
        "run_attempt": run_attempt,
    }
    failed_job = {"name": "pytest", "conclusion": "failure", "steps": []}
    jobs = [failed_job] if jobs is None else jobs
    previous = [
        dict(run, id=i + 1, conclusion=value, run_attempt=1) for i, value in enumerate(history)
    ]
    if pr_labels is None:
        pr_labels = [{"name": "agent:codex"}, {"name": "autofix"}]
    fixture = {
        "run": run,
        "history": previous + [run],
        "jobs": jobs,
        "historical_jobs": historical_jobs,
        "attempt_jobs": attempt_jobs or {},
        "pr_labels": pr_labels,
        "pr_body": pr_body,
    }
    # Only the GitHub/retry/registry boundary is replaced. All counting, filtering,
    # output wiring and escalation code comes from the shipped workflow YAML.
    harness = r"""
const fixture = JSON.parse(process.env.FIXTURE);
const output = {};
const labels = [];
const comments = [];
const core = {
  setOutput: (key, value) => output[key] = value,
  info: () => {}, warning: () => {}, setFailed: (message) => {throw Error(message);}
};
const context = {repo: {owner: 'stranske', repo: 'fixture'},
  payload: {workflow_run: fixture.run}};
const github = {rest: {actions: {
  getWorkflowRun: async () => ({data: fixture.run}),
  listWorkflowRuns: async (params) => {
    if (params.workflow_id !== 42 || params.head_sha !== 'current-head') {
      throw Error('Attempt history must query the triggering Gate and exact head');
    }
    return fixture.history;
  },
  listJobsForWorkflowRun: async (params) => params.run_id === 100 ? fixture.jobs :
    (fixture.historical_jobs ?? [{name: 'pytest', conclusion: 'failure'}]),
  listJobsForWorkflowRunAttempt: async (params) => {
    const attemptJobs = fixture.attempt_jobs[String(params.attempt_number)];
    if (attemptJobs) return attemptJobs;
    if (params.run_id === 100 && params.attempt_number === fixture.run.run_attempt) {
      return fixture.jobs;
    }
    return fixture.historical_jobs ?? [{name: 'pytest', conclusion: 'failure'}];
  }
}, pulls: {get: async () => ({data: {state: 'open', draft: false,
  head: {sha: 'current-head', ref: 'codex/issue-7', repo: {full_name: 'stranske/fixture'}},
  labels: fixture.pr_labels, body: fixture.pr_body}})},
issues: {addLabels: async (params) => labels.push(...params.labels),
  createComment: async (params) => comments.push(params.body)}}};
const withRetry = (fn) => fn(github);
const paginateWithRetry = (...args) => {
  const params = args.pop(); const method = args.pop(); return method(params);
};
const requireStub = (name) => {
  if (name === 'fs') return {existsSync: () => true};
  if (name.endsWith('github-api-with-retry.js')) return {
    withRetry, paginateWithRetry,
    createTokenAwareRetry: async () => ({withRetry, paginateWithRetry})};
  if (name.endsWith('agent_registry.js')) return {
    loadAgentRegistry: () => ({agents: {codex: {}}}), resolveAgentFromLabels: () => 'codex'};
  throw Error('Unexpected dependency: ' + name);
};
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
await new AsyncFunction('require', 'github', 'context', 'core', process.env.SCRIPT)(
  requireStub, github, context, core);
if (output.stop_reason === 'max_attempts') {
  const escalation = process.env.ESCALATION.replace(/\$\{\{([^}]+)\}\}/g, (_, expression) => {
    const key = expression.match(/needs\.prepare\.outputs\.(\w+)/)?.[1];
    if (!key) throw Error('Unexpected expression: ' + expression);
    return expression.includes('toJSON') ? JSON.stringify(output[key]) : output[key];
  });
  await new AsyncFunction('require', 'github', 'context', 'core', escalation)(
    requireStub, github, context, core);
}
console.log(JSON.stringify({output, labels, comments}));
"""
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", harness],
        cwd=tmp_path,
        env={
            **os.environ,
            "FIXTURE": json.dumps(fixture),
            "SCRIPT": script,
            "ESCALATION": escalation,
            "MANUAL_GATE_RUN_ID": "100",
            "MANUAL_PR_NUMBER": "7",
            "MANUAL_HEAD_SHA": "current-head",
        },
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("workflow", WORKFLOWS)
@pytest.mark.parametrize("conclusion", ["cancelled", "skipped", "success", "neutral", ""])
def test_cancelled_gate_never_escalates(workflow, tmp_path, conclusion):
    result = execute(workflow, tmp_path, conclusion, history=["cancelled"] * 8)
    assert result["output"]["should_run"] == "false"
    assert result["output"]["attempts"] == "0"
    assert "needs-human" not in result["labels"]
    assert not result["comments"]


@pytest.mark.parametrize("workflow", WORKFLOWS)
@pytest.mark.parametrize("previous_runs", [0, 3, 8])
def test_cancelled_only_head_never_exhausts_budget(workflow, tmp_path, previous_runs):
    """Concurrency cancellations cannot spend the budget or latch keepalive shut."""
    cancelled_jobs = [{"name": "pytest", "conclusion": "cancelled", "steps": []}]
    result = execute(
        workflow,
        tmp_path,
        "cancelled",
        history=["cancelled"] * previous_runs,
        jobs=cancelled_jobs,
        historical_jobs=cancelled_jobs,
    )
    output = result["output"]
    assert output["attempts"] == "0"
    assert int(output["attempts"]) < int(output["max_attempts"])
    assert output["stop_reason"] == "gate_not_failed"
    assert output["should_run"] == "false"
    assert "needs-human" not in result["labels"]
    assert not result["comments"]


@pytest.mark.parametrize("workflow", WORKFLOWS)
@pytest.mark.parametrize("conclusion", ["failure", "timed_out"])
def test_cancelled_history_does_not_spend_failure_budget(workflow, tmp_path, conclusion):
    result = execute(
        workflow, tmp_path, conclusion, history=["cancelled", "skipped", "success", "neutral"] * 4
    )
    assert result["output"]["should_run"] == "true"
    assert result["output"]["attempts"] == "1"
    assert "needs-human" not in result["labels"]


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_same_run_reruns_count_each_attempt(workflow, tmp_path):
    """Re-run jobs increments run_attempt on the same workflow run id."""
    failed_jobs = [{"name": "pytest", "conclusion": "failure", "steps": []}]
    attempt_jobs = {str(i): failed_jobs for i in range(1, 5)}
    result = execute(
        workflow,
        tmp_path,
        history=[],
        run_attempt=4,
        attempt_jobs=attempt_jobs,
    )
    assert result["output"]["should_run"] == "false"
    assert result["output"]["stop_reason"] == "max_attempts"
    assert result["output"]["attempts"] == "4"
    assert "gate attempts examined: 4" in result["comments"][0]


@pytest.mark.parametrize("workflow", WORKFLOWS)
@pytest.mark.parametrize("conclusion", ["failure", "timed_out"])
def test_jobless_gate_without_agent_label_does_not_add_escalated(workflow, tmp_path, conclusion):
    result = execute(
        workflow,
        tmp_path,
        conclusion,
        jobs=[],
        pr_labels=[],
        pr_body="",
    )
    assert result["output"]["stop_reason"] == "no_failing_jobs"
    assert result["output"]["should_run"] == "false"
    assert "autofix:escalated" not in result["labels"]
    assert not result["comments"]


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_real_failures_still_escalate(workflow, tmp_path):
    result = execute(workflow, tmp_path, history=["failure", "timed_out", "failure"])
    assert result["output"]["stop_reason"] == "max_attempts"
    assert result["output"]["attempts"] == "4"
    assert result["labels"] == ["needs-human"]
    assert "attempts with failing jobs: 4" in result["comments"][0]


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_same_run_attempt_counting_mutation_is_detected(workflow, tmp_path, monkeypatch):
    """Counting only unique run ids must break same-run rerun budgeting."""

    def regression():
        test_same_run_reruns_count_each_attempt(workflow, tmp_path)

    regression()
    original_read_text = Path.read_text
    source = original_read_text(ROOT / workflow)
    needle = "Number(gateRun.run_attempt) || 1"
    assert source.count(needle) >= 1, "Update the mutation for run_attempt counting"
    mutated = source.replace(needle, "1")

    def read_mutated(path, *args, **kwargs):
        if path == ROOT / workflow:
            return mutated
        return original_read_text(path, *args, **kwargs)

    with monkeypatch.context() as mutation:
        mutation.setattr(Path, "read_text", read_mutated)
        with pytest.raises(AssertionError):
            regression()

    regression()


@pytest.mark.parametrize("workflow", WORKFLOWS)
@pytest.mark.parametrize("conclusion", ["failure", "timed_out"])
@pytest.mark.parametrize(
    "jobs",
    [[]]
    + [
        [{"name": "pytest", "conclusion": value}]
        for value in ("cancelled", "skipped", "success", "neutral")
    ],
)
def test_jobless_gate_cannot_escalate_after_real_failures(workflow, tmp_path, conclusion, jobs):
    result = execute(workflow, tmp_path, conclusion, history=["failure"] * 8, jobs=jobs)
    assert result["output"]["stop_reason"] == "no_failing_jobs"
    assert "needs-human" not in result["labels"]
    assert not result["comments"]


@pytest.mark.parametrize("workflow", WORKFLOWS)
@pytest.mark.parametrize("conclusion", ["failure", "timed_out"])
@pytest.mark.parametrize(
    "historical_jobs",
    [[]]
    + [
        [{"name": "pytest", "conclusion": value}]
        for value in ("cancelled", "skipped", "success", "neutral")
    ],
)
def test_jobless_historical_failures_do_not_consume_budget(
    workflow, tmp_path, conclusion, historical_jobs
):
    """A failed run conclusion alone is insufficient evidence to spend the budget."""
    result = execute(workflow, tmp_path, history=[conclusion] * 8, historical_jobs=historical_jobs)
    assert result["output"]["should_run"] == "true"
    assert result["output"]["attempts"] == "1"
    assert "needs-human" not in result["labels"]
    assert not result["comments"]


@pytest.mark.parametrize("workflow", WORKFLOWS)
@pytest.mark.parametrize(
    "regression, argument, excluded_conclusion",
    [
        (test_cancelled_only_head_never_exhausts_budget, 8, "cancelled"),
        (test_cancelled_history_does_not_spend_failure_budget, "failure", "cancelled"),
        (test_cancelled_history_does_not_spend_failure_budget, "failure", "skipped"),
    ],
)
def test_nonfailure_counting_mutation_is_detected(
    workflow, tmp_path, monkeypatch, regression, argument, excluded_conclusion
):
    """Counting cancelled or skipped must break the regression, without editing YAML."""
    regression(workflow, tmp_path, argument)

    original_read_text = Path.read_text
    counted = "['failure', 'timed_out'].includes(String(value || '').toLowerCase())"

    source = original_read_text(ROOT / workflow)
    assert source.count(counted) == 1, "Update the mutation for the workflow predicate"
    mutated = source.replace(
        counted, counted.replace("'failure'", f"'failure', '{excluded_conclusion}'")
    )

    def read_mutated(path, *args, **kwargs):
        if path == ROOT / workflow:
            return mutated
        return original_read_text(path, *args, **kwargs)

    with monkeypatch.context() as mutation:
        mutation.setattr(Path, "read_text", read_mutated)
        with pytest.raises(AssertionError):
            regression(workflow, tmp_path, argument)

    regression(workflow, tmp_path, argument)


@pytest.mark.parametrize("workflow", WORKFLOWS)
@pytest.mark.parametrize("historical_failures", [0, 3])
def test_timed_out_jobs_enable_autofix_and_exhaust_budget(workflow, tmp_path, historical_failures):
    timed_out_jobs = [
        {
            "name": "pytest",
            "conclusion": "timed_out",
            "steps": [{"name": "Run tests", "conclusion": "timed_out"}],
        }
    ]
    result = execute(
        workflow,
        tmp_path,
        "failure",
        history=["failure"] * historical_failures,
        jobs=timed_out_jobs,
        historical_jobs=timed_out_jobs,
    )
    output = result["output"]
    assert output["attempts"] == str(historical_failures + 1)
    assert output["trigger_job"] == "pytest"
    assert output["trigger_step"] == "Run tests"
    if historical_failures:
        assert output["stop_reason"] == "max_attempts"
        assert output["should_run"] == "false"
        assert result["labels"] == ["needs-human"]
        assert "attempts with failing jobs: 4" in result["comments"][0]
    else:
        assert output["should_run"] == "true"
        assert not result["labels"]
        assert not result["comments"]


@pytest.mark.parametrize(
    "workflow, evidence",
    [(workflow, "evaluator") for workflow in WORKFLOWS]
    + [
        (workflow, evidence)
        for workflow in (
            ".github/workflows/autofix.yml",
            "templates/consumer-repo/.github/workflows/autofix.yml",
        )
        for evidence in ("check", "job")
    ],
)
def test_timed_out_eligibility_mutation_is_detected(workflow, evidence, tmp_path, monkeypatch):
    """Remove timeout eligibility in memory, require failure, then verify restoration."""

    def regression():
        if evidence == "evaluator":
            test_timed_out_jobs_enable_autofix_and_exhaust_budget(workflow, tmp_path, 0)
            test_timed_out_jobs_enable_autofix_and_exhaust_budget(workflow, tmp_path, 3)
        else:
            test_autofix_lint_failure_eligibility(
                workflow, tmp_path, evidence, "lint-ruff", "timed_out"
            )

    regression()
    original_read_text = Path.read_text
    source = original_read_text(ROOT / workflow)
    predicate = (
        "['failure', 'timed_out'].includes(String(value || '').toLowerCase())"
        if evidence == "evaluator"
        else "['failure', 'timed_out'].includes(("
        + ("cr" if evidence == "check" else "job")
        + ".conclusion || '').toLowerCase())"
    )
    assert source.count(predicate) == 1, "Update the mutation for the workflow predicate"
    mutated = source.replace(predicate, predicate.replace("'failure', 'timed_out'", "'failure'"))

    def read_mutated(path, *args, **kwargs):
        if path == ROOT / workflow:
            return mutated
        return original_read_text(path, *args, **kwargs)

    with monkeypatch.context() as mutation:
        mutation.setattr(Path, "read_text", read_mutated)
        with pytest.raises(AssertionError):
            regression()

    regression()
