"""Structural tests covering the Codex belt workflow pipeline.

These checks validate that the dispatcher, worker, and conveyor workflows
retain the critical wiring described in issue #2853. They guard the
automation pipeline against regressions by ensuring the YAML definitions keep
the PAT guards, dispatch wiring, and re-dispatch behaviour that Acceptance
Criteria rely upon.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
from typing import Any

import pytest
import yaml

WORKFLOW_ROOT = pathlib.Path(".github/workflows")


def _normalise_keys(node: Any) -> Any:
    if isinstance(node, dict):
        normalised: dict[str, Any] = {}
        for key, value in node.items():
            match key:
                case bool() as boolean:
                    key_str = "on" if boolean else str(boolean).lower()
                case str() as text:
                    key_str = text
                case other:
                    key_str = str(other)
            normalised[key_str] = _normalise_keys(value)
        return normalised
    if isinstance(node, list):
        return [_normalise_keys(item) for item in node]
    return node


def _load_workflow(slug: str) -> dict[str, Any]:
    path = WORKFLOW_ROOT / slug
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    assert isinstance(data, dict), f"Workflow {slug} should load into a mapping structure"
    return _normalise_keys(data)


def _step_runs_command(step: dict[str, Any], needle: str) -> bool:
    script = step.get("run") or ((step.get("with") or {}).get("script"))
    if not isinstance(script, str):
        return False
    return needle in script


def _iter_job_scripts(workflow: dict[str, Any]) -> list[tuple[str, str]]:
    scripts: list[tuple[str, str]] = []
    jobs = workflow.get("jobs") or {}
    for job in jobs.values():
        steps = job.get("steps") or []
        for step in steps:
            script = step.get("run") or ((step.get("with") or {}).get("script"))
            if isinstance(script, str):
                scripts.append((step.get("name", "<unnamed>"), script))
    return scripts


def _rest_calls_missing_retry(script: str, step_name: str) -> list[str]:
    failures: list[str] = []
    for match in re.finditer(r"github\.rest\.", script):
        window_start = max(0, match.start() - 250)
        window = script[window_start : match.start()]
        if "withRetry" not in window:
            line = script[: match.start()].count("\n") + 1
            failures.append(f"{step_name} line {line}")
    return failures


def test_dispatcher_is_reusable_and_exposes_worker_context():
    workflow = _load_workflow("agents-71-codex-belt-dispatcher.yml")
    triggers = workflow.get("on") or {}
    assert "workflow_call" in triggers
    assert "workflow_dispatch" in triggers

    workflow_call = triggers.get("workflow_call") or {}
    inputs = workflow_call.get("inputs") or {}
    assert {"force_issue", "dry_run"}.issubset(inputs)

    jobs = workflow.get("jobs") or {}
    dispatch_job = jobs.get("dispatch") or {}
    steps = dispatch_job.get("steps") or []
    assert steps, "Dispatcher job must define steps"

    # Check for multi-tier authentication flow (App token > PAT > GITHUB_TOKEN)
    step_names = [s.get("name", "") for s in steps]
    assert (
        "Mint GitHub App token (preferred)" in step_names
    ), "Dispatcher must attempt to mint GitHub App token first"
    assert (
        "Select authentication token (app > PAT > GITHUB_TOKEN)" in step_names
    ), "Dispatcher must have token selection step"
    select_step = next(
        s
        for s in steps
        if s.get("name") == "Select authentication token (app > PAT > GITHUB_TOKEN)"
    )
    assert _step_runs_command(
        select_step, "No authentication token available"
    ), "Dispatcher must fail when no token is available"

    assert not any(
        _step_runs_command(step, "createDispatchEvent") for step in steps
    ), "Dispatcher should no longer emit repository dispatch events"

    outputs = dispatch_job.get("outputs") or {}
    for key in {"issue", "branch", "base", "reason", "dry_run"}:
        assert key in outputs, f"Dispatcher must expose '{key}' output for orchestrator hand-off"


def test_worker_keeps_concurrency_and_pat_guard():
    workflow = _load_workflow("agents-72-codex-belt-worker.yml")

    concurrency = workflow.get("concurrency") or {}
    group = concurrency.get("group", "")
    assert group.startswith(
        "belt-${{ inputs.agent_key"
    ), f"Concurrency group should start with 'belt-${{ inputs.agent_key', got: {group}"
    assert "inputs.branch" in group, "Concurrency group must include branch to scope run"
    assert concurrency.get("cancel-in-progress") is True

    events = workflow.get("on") or {}
    assert set(events) == {"workflow_call"}

    jobs = workflow.get("jobs") or {}
    bootstrap = jobs.get("bootstrap") or {}
    steps = bootstrap.get("steps") or []
    assert steps, "Worker bootstrap job must define steps"

    # Check for multi-tier authentication flow (App token > PAT > GITHUB_TOKEN)
    step_names = [s.get("name", "") for s in steps]
    assert (
        "Mint GitHub App token (preferred)" in step_names
    ), "Worker must attempt to mint GitHub App token first"
    assert (
        "Select authentication token (app > PAT > GITHUB_TOKEN)" in step_names
    ), "Worker must have token selection step"
    select_step = next(
        s
        for s in steps
        if s.get("name") == "Select authentication token (app > PAT > GITHUB_TOKEN)"
    )
    assert _step_runs_command(
        select_step, "No authentication token available"
    ), "Worker must fail when no token is available"


def test_conveyor_requires_gate_success_and_retriggers_dispatcher():
    workflow = _load_workflow("agents-73-codex-belt-conveyor.yml")
    triggers = workflow.get("on") or {}
    workflow_call = triggers.get("workflow_call") or {}
    inputs = workflow_call.get("inputs") or {}
    assert {"issue", "branch", "pr_number"}.issubset(
        inputs
    ), "Conveyor callable contract must expose issue, branch, and pr_number inputs"

    jobs = workflow.get("jobs") or {}
    promote = jobs.get("promote") or {}
    steps = promote.get("steps") or []
    assert steps, "Conveyor promote job must define steps"

    # Check for multi-tier authentication flow (App token > PAT > GITHUB_TOKEN)
    step_names = [s.get("name", "") for s in steps]
    assert (
        "Mint GitHub App token (preferred)" in step_names
    ), "Conveyor must attempt to mint GitHub App token first"
    assert (
        "Select authentication token (app > PAT > GITHUB_TOKEN)" in step_names
    ), "Conveyor must have token selection step"
    select_step = next(
        s
        for s in steps
        if s.get("name") == "Select authentication token (app > PAT > GITHUB_TOKEN)"
    )
    assert _step_runs_command(
        select_step, "No authentication token available"
    ), "Conveyor must fail when no token is available"

    gate_steps = [step for step in steps if step.get("name") == "Ensure Gate succeeded"]
    assert gate_steps, "Conveyor must verify Gate success before merging"
    gate_script = (gate_steps[0].get("with") or {}).get("script", "")
    assert "getCombinedStatusForRef" in gate_script
    assert "conveyor requires success" in gate_script

    checkout_steps = [step for step in steps if step.get("name") == "Checkout retry helpers"]
    assert checkout_steps, "Conveyor must check out local helper scripts"
    checkout_sparse = (checkout_steps[0].get("with") or {}).get("sparse-checkout", "")
    assert (
        ".github/scripts/runtime_ac_merge_guard.js" in checkout_sparse
    ), "Conveyor sparse checkout must include the runtime AC merge guard helper"

    merge_steps = [step for step in steps if step.get("name") == "Merge PR with squash"]
    assert merge_steps, "Conveyor must define a merge step"
    merge_script = (merge_steps[0].get("with") or {}).get("script", "")
    assert "runtime_ac_merge_guard.js" in merge_script
    assert "assertRuntimeAcMergeAllowed" in merge_script
    assert "agents-73-codex-belt-conveyor" in merge_script

    redispatch_steps = [step for step in steps if step.get("name") == "Re-dispatch dispatcher"]
    assert redispatch_steps, "Conveyor must re-trigger the dispatcher"
    redispatch = redispatch_steps[0]
    script = (redispatch.get("with") or {}).get("script", "")
    assert "createWorkflowDispatch" in script
    assert "agents-71-codex-belt-dispatcher.yml" in script


# needs-human: update .github/workflows/agents-72-codex-belt-worker.yml to wrap
# github.rest.* calls with withRetry() and replace github.paginate with
# paginateWithRetry(); workflow edits require agent-high-privilege.
def test_worker_github_rest_calls_use_with_retry():
    workflow = _load_workflow("agents-72-codex-belt-worker.yml")
    failures: list[str] = []
    for step_name, script in _iter_job_scripts(workflow):
        failures.extend(_rest_calls_missing_retry(script, step_name))
    assert (
        not failures
    ), "Worker workflow has github.rest.* calls without withRetry(): " + ", ".join(sorted(failures))


def test_worker_pagination_uses_paginate_with_retry():
    if os.environ.get("AGENT_ENV", "agent-standard") != "agent-high-privilege":
        pytest.skip("needs-human: workflow updates require agent-high-privilege")
    workflow = _load_workflow("agents-72-codex-belt-worker.yml")
    failures: list[str] = []
    paginate_usage = 0
    for step_name, script in _iter_job_scripts(workflow):
        paginate_usage += script.count("paginateWithRetry(")
        for match in re.finditer(r"github\.paginate\b", script):
            line = script[: match.start()].count("\n") + 1
            failures.append(f"{step_name} line {line}")
    assert paginate_usage > 0, "Worker workflow should use paginateWithRetry() for pagination"
    assert (
        not failures
    ), "Worker workflow has github.paginate usage; replace with paginateWithRetry(): " + ", ".join(
        sorted(failures)
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="Activation script replay requires Node")
@pytest.mark.parametrize("root", [pathlib.Path("."), pathlib.Path("templates/consumer-repo")])
@pytest.mark.parametrize(
    "title",
    [
        "Fix the source of `KeyError: 'a'` in "
        "`tests/test_closer_pipeline.py::test_capacity_is_read_fresh_and_zero_defers`.",
        "Implement the documented behavior",
        "",
    ],
)
def test_worker_activation_preserves_the_task_title_as_data(root: pathlib.Path, title: str) -> None:
    path = root / WORKFLOW_ROOT / "agents-72-codex-belt-worker.yml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    step = next(
        step
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if step.get("name") == "Post activation comment"
    )
    script = step["with"]["script"]
    assert step["env"]["BELT_TASK_TITLE"] == "${{ steps.ledger_start.outputs.task_title }}"
    assert "steps.ledger_start.outputs.task_title" not in script
    for key, value in {
        "steps.pr.outputs.number": "4685",
        "steps.ctx.outputs.branch": "codex/issue-4555",
        "steps.mode.outputs.dry_run": "false",
        "steps.ledger_start.outputs.task_id": "task-01",
        "steps.ctx.outputs.agent_key": "codex",
    }.items():
        script = script.replace("${{ " + key + " }}", value)

    # Model only the activation comment surface. No real token or API client is loaded.
    runner = """
const assert = require('node:assert/strict');
const action = new (Object.getPrototypeOf(async () => {}).constructor)(
  'require', 'github', 'core', 'context', process.argv[1]);
const posted = [];
const issues = {
  listComments() {},
  createComment({body, issue_number}) {
    assert.equal(issue_number, 4685);
    posted.push(body);
  }
};
const fakeRequire = () => ({createTokenAwareRetry: async () => ({
  github: {rest:{issues}},
  withRetry: callback => callback({rest:{issues}}),
  paginateWithRetry: async () => [],
})});
action(fakeRequire, {}, {warning(message){throw Error(message);}},
  {repo:{owner:'stranske', repo:'Workflows'}}).then(() => {
  assert.equal(posted.length, 1);
  process.stdout.write(posted[0]);
}).catch(error => {console.error(error); process.exitCode = 1;});
"""
    completed = subprocess.run(
        ["node", "-e", runner, script],
        capture_output=True,
        check=True,
        text=True,
        env={"PATH": os.environ["PATH"], "BELT_TASK_TITLE": title},
    )
    assert "@codex start" in completed.stdout
    assert ("Focus on this task first" in completed.stdout) is bool(title)
    if title:
        assert f"**Focus on this task first:** `task-01` — {title}" in completed.stdout
