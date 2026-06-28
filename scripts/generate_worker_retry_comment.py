#!/usr/bin/env python3
"""Generate a needs-human PR comment for Codex belt worker retry updates."""

from __future__ import annotations

import argparse
import pathlib
import re
from typing import Any

import yaml

WORKFLOW_PATH = pathlib.Path(".github/workflows/agents-72-codex-belt-worker.yml")
REST_CALL_RE = re.compile(r"github\.rest\.")
PAGINATE_RE = re.compile(r"github\.paginate\b")


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


def _load_workflow(path: pathlib.Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Workflow {path} should load into a mapping structure")
    return _normalise_keys(data)


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


def _line_number(script: str, offset: int) -> int:
    return script[:offset].count("\n") + 1


def _format_step_location(step_name: str, line: int) -> str:
    return f"{step_name} line {line}"


def _detect_retry_loops(script: str, step_name: str) -> list[str]:
    failures: list[str] = []
    for match in REST_CALL_RE.finditer(script):
        window_start = max(0, match.start() - 250)
        window = script[window_start : match.start()]
        if "withRetry" not in window:
            failures.append(_format_step_location(step_name, _line_number(script, match.start())))
    return failures


def _rest_calls_missing_retry(script: str, step_name: str) -> list[str]:
    return _detect_retry_loops(script, step_name)


def _paginate_usages(script: str, step_name: str) -> list[str]:
    failures: list[str] = []
    for match in PAGINATE_RE.finditer(script):
        failures.append(_format_step_location(step_name, _line_number(script, match.start())))
    return failures


def _scan_scripts(workflow: dict[str, Any]) -> tuple[list[str], list[str]]:
    rest_failures: list[str] = []
    paginate_failures: list[str] = []
    for step_name, script in _iter_job_scripts(workflow):
        rest_failures.extend(_detect_retry_loops(script, step_name))
        paginate_failures.extend(_paginate_usages(script, step_name))
    return rest_failures, paginate_failures


def build_comment(workflow_path: pathlib.Path, include_label: bool = False) -> str:
    workflow = _load_workflow(workflow_path)
    rest_failures, paginate_failures = _scan_scripts(workflow)

    lines: list[str] = []
    if include_label:
        lines.append("Label: needs-human")
    lines.append(
        "Blocked by workflow protection: update .github/workflows/agents-72-codex-belt-worker.yml "
        "to wrap github.rest.* calls with withRetry() and replace github.paginate(...) with "
        "paginateWithRetry(...). Use createTokenAwareRetry() from "
        "./.github/scripts/github-api-with-retry.js for retry + token-rotation."
    )
    if rest_failures:
        lines.append("")
        lines.append("Unwrapped github.rest.* call sites:")
        for item in rest_failures:
            lines.append(f"- {item}")
    if paginate_failures:
        lines.append("")
        lines.append("github.paginate call sites to replace:")
        for item in paginate_failures:
            lines.append(f"- {item}")
    if not rest_failures and not paginate_failures:
        lines.append("")
        lines.append("No missing retry/pagination wrappers detected.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workflow",
        type=pathlib.Path,
        default=WORKFLOW_PATH,
        help="Path to the worker workflow YAML",
    )
    parser.add_argument(
        "--include-label",
        action="store_true",
        help="Include needs-human label line in the output",
    )
    args = parser.parse_args()
    print(build_comment(args.workflow, include_label=args.include_label))


if __name__ == "__main__":
    main()
