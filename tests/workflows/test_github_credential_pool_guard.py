"""Guards for GitHub credential-pool binding and setup-api-client ordering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

WORKFLOWS_DIR = Path(".github/workflows")
SETUP_ACTION = "./.github/actions/setup-api-client"


def _load_workflow_yaml(name: str) -> dict[str, Any]:
    data = yaml.safe_load((WORKFLOWS_DIR / name).read_text(encoding="utf-8")) or {}
    assert isinstance(data, dict)
    return data


def _step_uses(step: dict[str, Any], needle: str) -> bool:
    return step.get("uses") == needle


def _is_checkout_step(step: dict[str, Any]) -> bool:
    uses = step.get("uses") or ""
    return isinstance(uses, str) and uses.startswith("actions/checkout@")


def _last_checkout_index(steps: list[dict[str, Any]]) -> int | None:
    last: int | None = None
    for index, step in enumerate(steps):
        if _is_checkout_step(step):
            last = index
    return last


def _setup_api_client_indices(steps: list[dict[str, Any]]) -> list[int]:
    return [index for index, step in enumerate(steps) if _step_uses(step, SETUP_ACTION)]


def _assert_setup_after_final_checkout(job_name: str, steps: list[dict[str, Any]]) -> None:
    setup_indices = _setup_api_client_indices(steps)
    assert setup_indices, f"{job_name} must call setup-api-client"
    last_checkout = _last_checkout_index(steps)
    assert last_checkout is not None, f"{job_name} must checkout helpers before API work"
    for setup_index in setup_indices:
        assert setup_index > last_checkout, (
            f"{job_name}: setup-api-client must follow the final checkout "
            f"(checkout@{last_checkout}, setup@{setup_index})"
        )
    for index, step in enumerate(steps):
        if index <= setup_indices[-1]:
            continue
        assert not _is_checkout_step(step), (
            f"{job_name}: checkout step '{step.get('name')}' must not follow setup-api-client"
        )


def test_belt_scan_ready_prs_orders_setup_and_preflight():
    job = _load_workflow_yaml("reusable-70-orchestrator-main.yml")["jobs"]["belt-scan-ready-prs"]
    steps = job.get("steps") or []
    _assert_setup_after_final_checkout("belt-scan-ready-prs", steps)

    step_names = [step.get("name", "") for step in steps]
    scan_index = step_names.index("Preflight API budget and identify ready belt PRs")
    setup_index = step_names.index("Setup API client")
    assert setup_index < scan_index

    scan_script = (steps[scan_index].get("with") or {}).get("script", "")
    assert "failOpen: false" in scan_script
    assert "checkRateLimitStatus(api" in scan_script
    assert "identifyReadyCodexPRs({ github: api" in scan_script
    assert "reserveFraction" in scan_script
    assert "estimatedCost" in scan_script
    assert "core.setFailed" in scan_script
    assert scan_script.index("checkRateLimitStatus(api") < scan_script.index(
        "identifyReadyCodexPRs({ github: api"
    )


def test_automerge_agent_prs_installs_api_client_after_checkout():
    job = _load_workflow_yaml("reusable-70-orchestrator-main.yml")["jobs"]["automerge-agent-prs"]
    steps = job.get("steps") or []
    _assert_setup_after_final_checkout("automerge-agent-prs", steps)
    script = (steps[-1].get("with") or {}).get("script", "")
    assert "createTokenAwareRetry" in script
    assert "checkRateLimitStatus(api" in script
    assert "rateStatus.state !== 'safe'" in script
    assert "capabilities: ['pull-requests:write', 'contents:write', 'checks:read']" in script
    assert "withRetry((client)" in script
    assert script.index("checkRateLimitStatus(api") < script.index("withRetry((client)")


def test_agents_71_dispatcher_setup_survives_later_checkouts():
    job = _load_workflow_yaml("agents-71-codex-belt-dispatcher.yml")["jobs"]["dispatch"]
    steps = job.get("steps") or []
    setup_steps = [step for step in steps if _step_uses(step, SETUP_ACTION)]
    assert len(setup_steps) == 1, "Agents 71 must install the API client exactly once per dispatch job"
    setup_index = steps.index(setup_steps[0])
    workflows_checkout_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Checkout Workflows retry helpers"
    )
    assert setup_index > workflows_checkout_index
    install_dir = (setup_steps[0].get("with") or {}).get("install_dir", "")
    assert "runner.temp" in install_dir, "Agents 71 must install API deps outside workspace checkouts"

    stage_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Stage API helpers outside checkout clean path"
    )
    assert setup_index < stage_index
    stage_script = steps[stage_index].get("run", "")
    assert "RUNNER_TEMP" in stage_script
    assert "github-api-with-retry.js" in stage_script
    assert "github-rate-limited-wrapper.js" in stage_script

    for index, step in enumerate(steps[setup_index + 1 :], start=setup_index + 1):
        if _is_checkout_step(step):
            assert install_dir, "later checkouts require a stable install_dir"

    for step_name in ("Resolve candidate issue", "Transition issue to in-progress"):
        script_step = next(step for step in steps if step.get("name") == step_name)
        script = (script_step.get("with") or {}).get("script", "")
        assert "BELT_API_HELPER_DIR" in script
        assert "require('./.github/scripts/github-api-with-retry.js')" not in script
        assert "checkRateLimitStatus(api" in script
        assert "failOpen: false" in script
        assert "rateStatus.state !== 'safe'" in script
        assert script.index("checkRateLimitStatus(api") < script.index("withRetry((client)")


def test_orchestrator_init_rate_limit_check_is_fail_closed():
    job = _load_workflow_yaml("reusable-70-orchestrator-init.yml")["jobs"]["rate-limit-check"]
    assert job["outputs"]["safe"] == "${{ steps.check.outputs.safe || 'false' }}"
    assert job["outputs"]["state"] == "${{ steps.check.outputs.state || 'unknown' }}"
    assert "credential_pool_id" in job["outputs"]

    check_step = next(step for step in job["steps"] if step.get("id") == "check")
    script = (check_step.get("with") or {}).get("script", "")
    assert "failOpen: false" in script
    assert "credential_pool_id" in script
    assert "reserveFraction" in script
    assert "estimatedCost" in script
    assert "Proceeding with orchestrator run" not in script


def test_orchestrator_init_idle_precheck_uses_setup_api_client():
    job = _load_workflow_yaml("reusable-70-orchestrator-init.yml")["jobs"]["idle-precheck"]
    assert "outputs.state == 'safe'" in job["if"]
    steps = job.get("steps") or []
    _assert_setup_after_final_checkout("idle-precheck", steps)
    precheck_script = (steps[-1].get("with") or {}).get("script", "")
    assert "createTokenAwareRetry" in precheck_script
    assert "checkRateLimitStatus(api" in precheck_script
    assert "rateStatus.state !== 'safe'" in precheck_script
    assert "paginateWithRetry(api.rest.issues.listForRepo" in precheck_script
    assert "paginateWithRetry(\n                  github" not in precheck_script
    assert "credential_pool_id" in job["outputs"]
