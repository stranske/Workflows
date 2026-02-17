from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

WORKFLOW_PATHS = [
    Path(".github/workflows/agents-71-codex-belt-dispatcher.yml"),
    Path(".github/workflows/agents-72-codex-belt-worker.yml"),
    Path(".github/workflows/agents-73-codex-belt-conveyor.yml"),
    Path(".github/workflows/agents-verifier.yml"),
    Path(".github/workflows/reusable-agents-verifier.yml"),
    Path(".github/workflows/agents-verify-to-new-pr.yml"),
    Path(".github/workflows/agents-verify-to-issue-v2.yml"),
    Path(".github/workflows/agents-64-verify-agent-assignment.yml"),
    Path("templates/consumer-repo/.github/workflows/agents-71-codex-belt-dispatcher.yml"),
    Path("templates/consumer-repo/.github/workflows/agents-72-codex-belt-worker.yml"),
    Path("templates/consumer-repo/.github/workflows/agents-73-codex-belt-conveyor.yml"),
    Path("templates/consumer-repo/.github/workflows/agents-verifier.yml"),
    Path("templates/consumer-repo/.github/workflows/agents-verify-to-new-pr.yml"),
    Path("templates/consumer-repo/.github/workflows/agents-verify-to-issue-v2.yml"),
]

RETRY_HELPERS = (
    "withRetry",
    "withBackoff",
    "paginateWithRetry",
    "paginateWithBackoff",
)


def _normalise_keys(node: Any) -> Any:
    if isinstance(node, dict):
        normalised: dict[str, Any] = {}
        for key, value in node.items():
            key_str = ("on" if key else str(key).lower()) if isinstance(key, bool) else str(key)
            normalised[key_str] = _normalise_keys(value)
        return normalised
    if isinstance(node, list):
        return [_normalise_keys(item) for item in node]
    return node


def _load_workflow(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise AssertionError(f"Workflow {path} should load into a mapping structure")
    return _normalise_keys(data)


def _iter_job_scripts(workflow: dict[str, Any]) -> Iterable[tuple[str, str]]:
    jobs = workflow.get("jobs") or {}
    for job in jobs.values():
        steps = job.get("steps") or []
        for step in steps:
            script = step.get("run") or ((step.get("with") or {}).get("script"))
            if isinstance(script, str):
                yield step.get("name", "<unnamed>"), script


def _rest_calls_missing_retry(script: str, step_name: str, workflow_path: Path) -> list[str]:
    failures: list[str] = []
    for match in re.finditer(r"github\.rest\.", script):
        window_start = max(0, match.start() - 250)
        window = script[window_start : match.start()]
        if not any(helper in window for helper in RETRY_HELPERS):
            line = script[: match.start()].count("\n") + 1
            failures.append(f"{workflow_path.as_posix()}::{step_name} line {line}")
    return failures


def _paginate_calls(script: str, step_name: str, workflow_path: Path) -> list[str]:
    failures: list[str] = []
    for match in re.finditer(r"github\.paginate\b", script):
        line = script[: match.start()].count("\n") + 1
        failures.append(f"{workflow_path.as_posix()}::{step_name} line {line}")
    return failures


def test_retry_wrappers_cover_rest_calls() -> None:
    failures: list[str] = []
    for relative_path in WORKFLOW_PATHS:
        workflow_path = REPO_ROOT / relative_path
        assert workflow_path.exists(), f"Missing workflow: {relative_path}"
        workflow = _load_workflow(workflow_path)
        for step_name, script in _iter_job_scripts(workflow):
            failures.extend(_rest_calls_missing_retry(script, step_name, relative_path))
    assert not failures, (
        "GitHub REST calls must be wrapped in retry helpers (withRetry/withBackoff or "
        "paginateWithRetry/paginateWithBackoff): " + ", ".join(sorted(failures))
    )


def test_retry_wrappers_cover_pagination() -> None:
    failures: list[str] = []
    for relative_path in WORKFLOW_PATHS:
        workflow_path = REPO_ROOT / relative_path
        assert workflow_path.exists(), f"Missing workflow: {relative_path}"
        workflow = _load_workflow(workflow_path)
        for step_name, script in _iter_job_scripts(workflow):
            failures.extend(_paginate_calls(script, step_name, relative_path))
    assert (
        not failures
    ), "Use paginateWithRetry/paginateWithBackoff instead of github.paginate: " + ", ".join(
        sorted(failures)
    )
