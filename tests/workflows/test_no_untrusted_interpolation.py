"""Regression guard for free-text Actions values embedded in scripts.

Workflow expressions are evaluated before a shell or github-script body runs.
The listed values are free-form workflow-dispatch or runner inputs, so placing
them directly in a ``run:``/``with.script:`` body can turn quotes or shell
metacharacters into source code. They must cross that boundary through a
step-level ``env:`` value instead.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_GLOBS = (".github/workflows/*.yml", ".github/workflows/*.yaml")

# Keep this deliberately small. Other expressions require a file-by-file
# constrained-value review; expanding this set is not a substitute for that
# review.
UNTRUSTED_EXPRESSIONS = frozenset({"inputs.commit_message", "inputs.codex_args", "inputs.repos"})
ACTIONS_EXPRESSION = re.compile(r"\$\{\{(?P<body>.*?)\}\}", re.DOTALL)


def _workflow_paths() -> Iterable[Path]:
    for pattern in WORKFLOW_GLOBS:
        yield from sorted(ROOT.glob(pattern))


def _script_values(path: Path) -> Iterable[tuple[str, str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for job_name, job in (data.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for index, step in enumerate(job.get("steps") or []):
            if not isinstance(step, dict):
                continue
            run = step.get("run")
            if isinstance(run, str):
                yield f"{job_name}/step-{index}/run", run
            script = (step.get("with") or {}).get("script")
            if isinstance(script, str):
                yield f"{job_name}/step-{index}/with.script", script


def _untrusted_references(script: str) -> list[str]:
    """Return free-text inputs referenced anywhere in Actions expressions."""

    expression_bodies = [match.group("body") for match in ACTIONS_EXPRESSION.finditer(script)]
    return sorted(
        expression
        for expression in UNTRUSTED_EXPRESSIONS
        if any(
            re.search(rf"\b{re.escape(expression)}\b", body)
            for body in expression_bodies
        )
    )


def test_no_untrusted_expressions_in_script_bodies() -> None:
    """Free-text inputs must not be interpolated into shell or JS source."""
    violations: list[str] = []
    for workflow in _workflow_paths():
        for location, script in _script_values(workflow):
            for expression in _untrusted_references(script):
                violations.append(f"{workflow.relative_to(ROOT)}:{location}: {expression}")
    assert not violations, (
        "Pass untrusted workflow values through step env and consume the env "
        "variable in the script:\n" + "\n".join(violations)
    )


@pytest.mark.parametrize("expression", sorted(UNTRUSTED_EXPRESSIONS))
def test_untrusted_expression_guard_has_a_concrete_target(expression: str) -> None:
    """Keep each listed field intentional rather than a broad catch-all."""
    assert expression.startswith("inputs.")


def test_untrusted_expression_guard_matches_default_and_wrapper_forms() -> None:
    assert _untrusted_references("echo ${{ inputs.repos || 'all' }}") == ["inputs.repos"]
    assert _untrusted_references("const v = '${{ format('{0}', inputs.codex_args) }}';") == [
        "inputs.codex_args"
    ]
