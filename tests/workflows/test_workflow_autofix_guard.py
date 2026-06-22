"""Workflow guard regression tests for autofix automation."""

from __future__ import annotations

import pathlib
import re
import subprocess
from typing import Any

import yaml

WORKFLOWS = pathlib.Path(".github/workflows")
GITHUB_SCRIPTS = pathlib.Path(".github/scripts")


def _load_yaml(name: str) -> dict[str, Any]:
    with (WORKFLOWS / name).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _guarded_follow_up_steps(steps: list[dict[str, Any]], guard_id: str = "guard") -> list[str]:
    """Return the names of steps after ``guard_id`` lacking guard
    conditions."""
    missing: list[str] = []
    try:
        guard_index = next(index for index, step in enumerate(steps) if step.get("id") == guard_id)
    except StopIteration as exc:  # pragma: no cover - defensive: workflow must define guard
        raise AssertionError(f"Guard step '{guard_id}' missing") from exc

    for step in steps[guard_index + 1 :]:
        condition = step.get("if")
        # Summary/always steps are allowed to run regardless so they can document the skip.
        if isinstance(condition, str) and "always()" in condition:
            continue
        if condition is None or "steps.guard.outputs.skip" not in str(condition):
            missing.append(step.get("name", "<unnamed>"))
    return missing


GATE_WORKFLOW = WORKFLOWS / "pr-00-gate.yml"
HELPER_FILE = "maint-post-ci.js"


def test_gate_summary_uses_post_ci_helper() -> None:
    contents = GATE_WORKFLOW.read_text(encoding="utf-8")
    assert "./.github/scripts/maint-post-ci.js" in contents


def test_autofix_loop_does_not_subscribe_to_workflow_job_events() -> None:
    data = _load_yaml("autofix.yml")
    triggers = data.get("on") or data.get(True) or {}
    assert "workflow_run" in triggers
    assert "pull_request_target" in triggers
    assert (
        "workflow_job" not in triggers
    ), "workflow_job events create noisy push-associated autofix runs with no correctness gain"


def test_agents_autofix_loop_uses_direct_retry_helper_contract() -> None:
    """Direct retry helper calls must close over ``github`` in github-script."""
    contents = (WORKFLOWS / "agents-autofix-loop.yml").read_text(encoding="utf-8")
    assert "withRetry((client)" not in contents
    assert "github.rest.actions.getWorkflowRun" in contents


def test_agents_autofix_loop_skips_rate_limited_gate_lookup() -> None:
    contents = (WORKFLOWS / "agents-autofix-loop.yml").read_text(encoding="utf-8")
    assert "workflow-run-lookup-rate-limited" in contents
    assert "gate run lookup rate-limited" in contents
    assert "isRateLimitError(error)" in contents


def test_reusable_autofix_guard_applies_to_all_steps() -> None:
    data = _load_yaml("reusable-18-autofix.yml")
    steps = data["jobs"]["autofix"]["steps"]
    missing = _guarded_follow_up_steps(steps)
    assert not missing, f"Reusable autofix steps missing guard condition: {missing}"


def test_reusable_autofix_allows_patless_fallback() -> None:
    data = _load_yaml("reusable-18-autofix.yml")
    triggers = data.get("on") or data.get(True) or {}
    secrets = triggers["workflow_call"]["secrets"]["service_bot_pat"]
    assert secrets.get("required") is False

    steps: list[dict[str, Any]] = data["jobs"]["autofix"]["steps"]
    checkout = next(step for step in steps if step.get("name") == "Checkout PR HEAD")
    assert "AUTOFIX_TOKEN" in checkout.get("with", {}).get("token", ""), checkout


def test_reusable_autofix_splits_push_and_patch_paths() -> None:
    """Test that autofix correctly splits between push and patch delivery paths."""
    data = _load_yaml("reusable-18-autofix.yml")
    steps: list[dict[str, Any]] = data["jobs"]["autofix"]["steps"]
    commit_step = next(step for step in steps if step.get("name") == "Commit changes (push path)")
    patch_step = next(
        step for step in steps if step.get("name") == "Create patch artifact (fallback)"
    )

    # Push path uses AUTOFIX_CAN_PUSH flag (works for both PAT and App tokens in same-repo)
    assert "env.AUTOFIX_CAN_PUSH == 'true'" in (commit_step.get("if") or "")
    # Patch fallback is for when push isn't possible (forks, dry-run, missing creds)
    assert "env.AUTOFIX_CAN_PUSH != 'true'" in (patch_step.get("if") or "")


def _resolve_workflows_ref(workflow_ref: str, tmp_path: pathlib.Path) -> str:
    data = _load_yaml("reusable-18-autofix.yml")
    steps: list[dict[str, Any]] = data["jobs"]["autofix"]["steps"]
    step = next(step for step in steps if step.get("name") == "Determine Workflows workflow ref")
    output = tmp_path / "github-output.txt"
    subprocess.run(
        ["bash", "-c", step["run"]],
        check=True,
        env={"WORKFLOW_REF": workflow_ref, "GITHUB_OUTPUT": str(output)},
    )
    values = dict(
        line.split("=", 1)
        for line in output.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    return values["ref"]


def test_reusable_autofix_uses_main_for_consumer_workflow_refs(tmp_path: pathlib.Path) -> None:
    ref = _resolve_workflows_ref(
        "stranske/Workflows-Integration-Tests/.github/workflows/autofix.yml@refs/pull/34/merge",
        tmp_path,
    )
    assert ref == "main"


def test_reusable_autofix_preserves_workflows_repo_refs(tmp_path: pathlib.Path) -> None:
    ref = _resolve_workflows_ref(
        "stranske/Workflows/.github/workflows/autofix.yml@refs/pull/2470/merge",
        tmp_path,
    )
    assert ref == "refs/pull/2470/merge"


def _load_helper(name: str) -> str:
    helper_path = GITHUB_SCRIPTS / name
    assert helper_path.exists(), f"Expected helper script to exist: {name}"
    return helper_path.read_text(encoding="utf-8")


def _extract_trivial_keywords(source: str) -> set[str]:
    patterns = (
        r"TRIVIAL_KEYWORDS\s*\|\|\s*'([^']+)'",
        r"AUTOFIX_TRIVIAL_KEYWORDS\s*\|\|\s*'([^']+)'",
    )
    match = None
    for pattern in patterns:
        match = re.search(pattern, source)
        if match:
            break
    if not match:
        raise AssertionError("Default AUTOFIX_TRIVIAL_KEYWORDS clause missing from autofix helper")
    return {token.strip() for token in match.group(1).split(",") if token.strip()}


def test_autofix_trivial_keywords_cover_lint_type_and_tests() -> None:
    helper_source = _load_helper(HELPER_FILE)
    keywords = _extract_trivial_keywords(helper_source)
    expected = {"lint", "mypy", "test"}
    missing = expected.difference(keywords)
    assert not missing, f"Autofix trivial keywords missing expected tokens: {missing}"
    assert "label" in keywords, "Label failures should remain autofix-eligible"
