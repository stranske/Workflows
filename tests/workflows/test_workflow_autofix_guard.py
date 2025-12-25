"""Workflow guard regression tests for autofix automation."""

from __future__ import annotations

import pathlib
import re
from typing import Any, Dict, List

import yaml

WORKFLOWS = pathlib.Path(".github/workflows")
GITHUB_SCRIPTS = pathlib.Path(".github/scripts")


def _load_yaml(name: str) -> Dict[str, Any]:
    with (WORKFLOWS / name).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _guarded_follow_up_steps(steps: List[Dict[str, Any]], guard_id: str = "guard") -> List[str]:
    """Return the names of steps after ``guard_id`` lacking guard
    conditions."""
    missing: List[str] = []
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

    steps: List[Dict[str, Any]] = data["jobs"]["autofix"]["steps"]
    checkout = next(step for step in steps if step.get("name") == "Checkout PR HEAD")
    assert "AUTOFIX_TOKEN" in checkout.get("with", {}).get("token", ""), checkout


def test_reusable_autofix_splits_push_and_patch_paths() -> None:
    """Test that autofix correctly splits between push and patch delivery paths."""
    data = _load_yaml("reusable-18-autofix.yml")
    steps: List[Dict[str, Any]] = data["jobs"]["autofix"]["steps"]
    commit_step = next(step for step in steps if step.get("name") == "Commit changes (push path)")
    patch_step = next(
        step for step in steps if step.get("name") == "Create patch artifact (fallback)"
    )

    # Push path uses AUTOFIX_CAN_PUSH flag (works for both PAT and App tokens in same-repo)
    assert "env.AUTOFIX_CAN_PUSH == 'true'" in (commit_step.get("if") or "")
    # Patch fallback is for when push isn't possible (forks, dry-run, missing creds)
    assert "env.AUTOFIX_CAN_PUSH != 'true'" in (patch_step.get("if") or "")


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
