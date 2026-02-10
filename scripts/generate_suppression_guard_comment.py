#!/usr/bin/env python3
"""Generate a needs-human comment for suppression guard workflow updates."""

from __future__ import annotations

import argparse
import pathlib
import re
from collections.abc import Iterable, Sequence
from typing import Any

import yaml

DEFAULT_WORKFLOWS = (
    pathlib.Path(".github/workflows/agents-keepalive-loop.yml"),
    pathlib.Path(".github/workflows/autofix.yml"),
    pathlib.Path(".github/workflows/reusable-18-autofix.yml"),
)

SCRIPT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?:github|octokit)(?:\.rest)?\.issues\.createComment\b"),
        "issues.createComment",
    ),
    (
        re.compile(r"(?:github|octokit)(?:\.rest)?\.pulls\.createReview\b"),
        "pulls.createReview",
    ),
    (
        re.compile(r"(?:github|octokit)(?:\.rest)?\.pulls\.createReviewComment\b"),
        "pulls.createReviewComment",
    ),
    (re.compile(r"\\bgh\\s+pr\\s+comment\\b"), "gh pr comment"),
    (re.compile(r"\\bgh\\s+pr\\s+review\\b"), "gh pr review"),
)

ACTION_HINTS: tuple[tuple[str, str], ...] = (
    ("peter-evans/create-or-update-comment", "create-or-update-comment action"),
    ("peter-evans/create-pull-request", "create-pull-request action"),
    ("marocchino/sticky-pull-request-comment", "sticky-pull-request-comment action"),
)

# Matches suppress_comments in a negation context so that an inverted guard
# like ``inputs.suppress_comments == true`` is NOT treated as a valid guard.
_SUPPRESS_NEGATION_RE = re.compile(
    r"suppress_comments\s*!=\s*true"
    r"|suppress_comments\s*==\s*false"
    r"|!\s*inputs\.suppress_comments"
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


def _load_workflow(path: pathlib.Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Workflow {path} should load into a mapping structure")
    return _normalise_keys(data)


def _step_script(step: dict[str, Any]) -> str:
    run = step.get("run")
    if isinstance(run, str):
        return run
    with_block = step.get("with") or {}
    script = with_block.get("script")
    if isinstance(script, str):
        return script
    return ""


def _step_action_hint(step: dict[str, Any]) -> str | None:
    uses = step.get("uses")
    if not isinstance(uses, str):
        return None
    lower = uses.lower()
    for needle, label in ACTION_HINTS:
        if needle in lower:
            return label
    return None


def _match_patterns(script: str) -> list[str]:
    matches: list[str] = []
    for pattern, label in SCRIPT_PATTERNS:
        if pattern.search(script):
            matches.append(label)
    return matches


def _iter_posting_steps(workflow: dict[str, Any]) -> list[tuple[str, str, list[str]]]:
    findings: list[tuple[str, str, list[str]]] = []
    jobs = workflow.get("jobs") or {}
    for job_id, job in jobs.items():
        job_if = job.get("if")
        job_if_str = job_if if isinstance(job_if, str) else ""
        steps = job.get("steps") or []
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            name = step.get("name") or step.get("id") or f"step-{index}"
            script = _step_script(step)
            hints = _match_patterns(script)
            action_hint = _step_action_hint(step)
            if action_hint:
                hints.append(action_hint)
            step_if = step.get("if")
            step_if_str = step_if if isinstance(step_if, str) else ""
            guarded = (
                "should_post_review" in job_if_str
                or "should_post_review" in step_if_str
                or bool(_SUPPRESS_NEGATION_RE.search(job_if_str))
                or bool(_SUPPRESS_NEGATION_RE.search(step_if_str))
            )
            if hints and not guarded:
                findings.append((str(job_id), str(name), hints))
    return findings


def _format_findings(
    workflow_path: pathlib.Path, findings: Sequence[tuple[str, str, list[str]]]
) -> list[str]:
    lines: list[str] = []
    lines.append(f"Workflow: {workflow_path}")
    if not findings:
        lines.append(
            "- No unguarded PR comment/review posting steps detected "
            "(or posting steps are already guarded)."
        )
        return lines
    for job_id, step_name, hints in findings:
        hint_str = ", ".join(sorted(set(hints)))
        lines.append(f"- {job_id} / {step_name} ({hint_str})")
    return lines


def build_comment(workflows: Iterable[pathlib.Path], include_label: bool = False) -> str:
    lines: list[str] = []
    if include_label:
        lines.append("Label: needs-human")
    lines.append(
        "Blocked by workflow protection: update "
        ".github/workflows/agents-keepalive-loop.yml, "
        ".github/workflows/autofix.yml, and "
        ".github/workflows/reusable-18-autofix.yml to add explicit `if:` guards "
        "on every step/job that posts a PR comment or PR review so they cannot "
        "run when suppression is active. "
        "Use the suppression output key `should_post_review` (from "
        ".github/scripts/should-post-review.js) or the `suppress_comments` "
        "input to gate the posting steps."
    )
    lines.append("")

    for workflow_path in workflows:
        if not workflow_path.exists():
            lines.append(f"Workflow: {workflow_path}")
            lines.append("- Workflow file not found in repository.")
            lines.append("")
            continue
        workflow = _load_workflow(workflow_path)
        findings = _iter_posting_steps(workflow)
        lines.extend(_format_findings(workflow_path, findings))
        lines.append("")

    if lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workflow",
        action="append",
        type=pathlib.Path,
        dest="workflows",
        help="Path to a workflow YAML file (repeatable). Defaults to keepalive/autofix.",
    )
    parser.add_argument(
        "--include-label",
        action="store_true",
        help="Include needs-human label line in the output.",
    )
    args = parser.parse_args()
    workflows = tuple(args.workflows) if args.workflows else DEFAULT_WORKFLOWS
    print(build_comment(workflows, include_label=args.include_label))


if __name__ == "__main__":
    main()
