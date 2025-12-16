"""Structural tests covering the Codex belt workflow pipeline.

These checks validate that the dispatcher, worker, and conveyor workflows
retain the critical wiring described in issue #2853. They guard the
automation pipeline against regressions by ensuring the YAML definitions keep
the PAT guards, dispatch wiring, and re-dispatch behaviour that Acceptance
Criteria rely upon.
"""

from __future__ import annotations

import pathlib
from typing import Any

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


def test_dispatcher_is_reusable_only_and_exposes_worker_context():
    workflow = _load_workflow("agents-71-codex-belt-dispatcher.yml")
    triggers = workflow.get("on") or {}
    assert set(triggers) == {"workflow_call"}

    workflow_call = triggers.get("workflow_call") or {}
    inputs = workflow_call.get("inputs") or {}
    assert {"force_issue", "dry_run"}.issubset(inputs)

    jobs = workflow.get("jobs") or {}
    dispatch_job = jobs.get("dispatch") or {}
    steps = dispatch_job.get("steps") or []
    assert steps, "Dispatcher job must define steps"

    guard = steps[0]
    assert guard.get("name") == "Ensure ACTIONS_BOT_PAT is configured"
    assert _step_runs_command(
        guard, "ACTIONS_BOT_PAT secret is required for dispatcher writes."
    ), "Dispatcher must fail early when ACTIONS_BOT_PAT is missing"

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
        "codex-belt"
    ), f"Concurrency group should start with 'codex-belt', got: {group}"
    assert concurrency.get("cancel-in-progress") is True

    events = workflow.get("on") or {}
    assert set(events) == {"workflow_call"}

    jobs = workflow.get("jobs") or {}
    bootstrap = jobs.get("bootstrap") or {}
    steps = bootstrap.get("steps") or []
    assert steps, "Worker bootstrap job must define steps"
    guard = steps[0]
    assert guard.get("name") == "Ensure ACTIONS_BOT_PAT is configured"
    assert _step_runs_command(guard, "ACTIONS_BOT_PAT secret is required for worker actions.")


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

    guard = steps[0]
    assert guard.get("name") == "Ensure ACTIONS_BOT_PAT is configured"
    assert _step_runs_command(guard, "ACTIONS_BOT_PAT secret is required for conveyor actions.")

    gate_steps = [step for step in steps if step.get("name") == "Ensure Gate succeeded"]
    assert gate_steps, "Conveyor must verify Gate success before merging"
    gate_script = (gate_steps[0].get("with") or {}).get("script", "")
    assert "getCombinedStatusForRef" in gate_script
    assert "conveyor requires success" in gate_script

    redispatch_steps = [step for step in steps if step.get("name") == "Re-dispatch dispatcher"]
    assert redispatch_steps, "Conveyor must re-trigger the dispatcher"
    redispatch = redispatch_steps[0]
    script = (redispatch.get("with") or {}).get("script", "")
    assert "createWorkflowDispatch" in script
    assert "agents-71-codex-belt-dispatcher.yml" in script
