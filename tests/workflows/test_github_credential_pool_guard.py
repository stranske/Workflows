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
        assert not _is_checkout_step(
            step
        ), f"{job_name}: checkout step '{step.get('name')}' must not follow setup-api-client"


def test_belt_scan_ready_prs_orders_setup_and_preflight():
    workflow = _load_workflow_yaml("agents-73-codex-belt-conveyor-dispatch.yml")
    job = workflow["jobs"]["belt-scan-ready-prs"]
    assert job["env"]["BELT_AGENT"] == "codex"
    steps = job.get("steps") or []
    _assert_setup_after_final_checkout("belt-scan-ready-prs", steps)

    step_names = [step.get("name", "") for step in steps]
    scan_index = step_names.index("Preflight API budget and identify ready belt PRs")
    setup_index = step_names.index("Setup API client")
    assert setup_index < scan_index

    scan_script = (steps[scan_index].get("with") or {}).get("script", "")
    assert "failOpen: false" in scan_script
    assert "checkRateLimitStatus(api" in scan_script
    assert "identifyReadyBeltPRs({ github: api" in scan_script
    assert "reserveFraction: 0.15" in scan_script
    assert "estimatedCost: 250" in scan_script
    assert "core.setFailed" in scan_script
    assert scan_script.index("checkRateLimitStatus(api") < scan_script.index(
        "identifyReadyBeltPRs({ github: api"
    )


def test_belt_preview_stays_with_read_token_and_never_invokes_writer():
    workflow = _load_workflow_yaml("agents-73-codex-belt-conveyor-dispatch.yml")
    trigger = workflow[True]  # PyYAML parses the GitHub `on` key as true.
    assert set(trigger) == {"workflow_dispatch"}
    inputs = trigger["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"dry_run", "max_promotions"}
    assert inputs["dry_run"]["type"] == "boolean"
    assert inputs["dry_run"]["default"] is True
    assert inputs["max_promotions"]["default"] == 2
    assert workflow["permissions"] == {}
    scan = workflow["jobs"]["belt-scan-ready-prs"]
    assert "github.ref_protected" in scan["if"]
    assert "github.event.repository.default_branch" in scan["if"]
    assert "stranske/Workflows" in scan["if"]
    assert "agent-high-privilege" in scan["environment"]["name"]
    assert set(scan["permissions"].values()) == {"read"}
    validation, checkout, setup, probe = scan["steps"]
    assert "^[0-5]$" in validation["run"]
    assert checkout["with"]["persist-credentials"] is False
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert all(step["if"] == "inputs.max_promotions > 0" for step in (checkout, setup, probe))
    for name, value in setup["with"].items():
        if name != "github_token":
            assert "!inputs.dry_run && secrets." in value

    promote = workflow["jobs"]["belt-conveyor"]
    assert promote["needs"] == "belt-scan-ready-prs"
    assert "!inputs.dry_run" in promote["if"]
    assert promote["strategy"]["matrix"]["pr"] == (
        "${{ fromJSON(needs.belt-scan-ready-prs.outputs.items) }}"
    )
    assert promote["with"]["head_sha"] == "${{ matrix.pr.head_sha }}"
    assert set(promote["secrets"]) == {"ACTIONS_BOT_PAT"}


def test_agents_73_conveyor_keeps_its_api_client_and_live_write_guards():
    job = _load_workflow_yaml("agents-73-codex-belt-conveyor.yml")["jobs"]["promote"]
    steps = job.get("steps") or []
    _assert_setup_after_final_checkout("promote", steps)
    write_steps = [
        step
        for step in steps
        if any(
            method in (step.get("with") or {}).get("script", "")
            for method in ("rest.pulls.merge(", "rest.git.deleteRef(", "rest.issues.createComment(")
        )
    ]
    assert write_steps
    assert all("dry_run != 'true'" in step["if"] for step in write_steps)


def test_source_and_shipped_conveyor_share_one_validated_head_for_status_and_merge():
    for directory in (WORKFLOWS_DIR, Path("templates/consumer-repo") / WORKFLOWS_DIR):
        workflow = yaml.safe_load((directory / "agents-73-codex-belt-conveyor.yml").read_text())
        steps = {step.get("id"): step for step in workflow["jobs"]["promote"]["steps"]}
        load_pr = steps["pr"]
        assert load_pr["env"]["EXPECTED_HEAD_SHA"] == "${{ inputs.head_sha }}"
        script = load_pr["with"]["script"]
        assert "expectedHead && expectedHead !== headSha" in script
        assert "head changed after belt selection" in script
        assert "core.setOutput('head_sha', headSha)" in script
        for key in ("gate", "merge"):
            assert steps[key]["env"]["CHECKED_HEAD_SHA"] == "${{ steps.pr.outputs.head_sha }}"
            assert "process.env.CHECKED_HEAD_SHA" in steps[key]["with"]["script"]
        assert "ref: headSha" in steps["gate"]["with"]["script"]
        assert "sha: headSha" in steps["merge"]["with"]["script"]


def test_agents_71_dispatcher_setup_survives_later_checkouts():
    job = _load_workflow_yaml("agents-71-codex-belt-dispatcher.yml")["jobs"]["dispatch"]
    steps = job.get("steps") or []
    setup_steps = [step for step in steps if _step_uses(step, SETUP_ACTION)]
    assert (
        len(setup_steps) == 1
    ), "Agents 71 must install the API client exactly once per dispatch job"
    setup_index = steps.index(setup_steps[0])
    workflows_checkout_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Checkout Workflows retry helpers"
    )
    assert setup_index > workflows_checkout_index
    install_dir = (setup_steps[0].get("with") or {}).get("install_dir", "")
    assert (
        "runner.temp" in install_dir
    ), "Agents 71 must install API deps outside workspace checkouts"

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

    for _index, step in enumerate(steps[setup_index + 1 :], start=setup_index + 1):
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
