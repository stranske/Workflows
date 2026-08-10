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


def _actions_expression_bodies(script: str) -> Iterable[str]:
    """Yield Actions expression bodies without ending quoted brace literals early."""

    start = 0
    while (opening := script.find("${{", start)) != -1:
        index = opening + 3
        quote: str | None = None
        escaped = False
        while index < len(script) - 1:
            character = script[index]
            if quote:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
            elif character in {"'", '"'}:
                quote = character
            elif script[index : index + 2] == "}}":
                yield script[opening + 3 : index]
                start = index + 2
                break
            index += 1
        else:
            start = opening + 3


def _references_untrusted_input(body: str, expression: str) -> bool:
    """Recognize equivalent property and bracket references in an expression."""

    _, property_name = expression.split(".", maxsplit=1)
    return bool(
        re.search(
            rf"\binputs\s*(?:\.\s*{re.escape(property_name)}\b|\[\s*['\"]{re.escape(property_name)}['\"]\s*\])",
            body,
        )
    )


def _untrusted_references(script: str) -> list[str]:
    """Return free-text inputs referenced anywhere in Actions expressions."""

    expression_bodies = list(_actions_expression_bodies(script))
    return sorted(
        expression
        for expression in UNTRUSTED_EXPRESSIONS
        if any(_references_untrusted_input(body, expression) for body in expression_bodies)
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


@pytest.mark.parametrize(
    ("body", "expression", "expected"),
    [
        ("inputs.commit_message", "inputs.commit_message", True),
        ("inputs['commit_message']", "inputs.commit_message", True),
        ("inputs.repos || 'all'", "inputs.repos", True),
        ("inputs['repos']", "inputs.repos", True),
        ("inputs.codex_args", "inputs.codex_args", True),
        ("inputs.safe_field", "inputs.commit_message", False),
    ],
)
def test_references_untrusted_input(body: str, expression: str, expected: bool) -> None:
    assert _references_untrusted_input(body, expression) is expected


@pytest.mark.parametrize("expression", sorted(UNTRUSTED_EXPRESSIONS))
def test_untrusted_expression_guard_detects_listed_inputs(expression: str) -> None:
    """Each listed field must be detectable via _untrusted_references."""

    property_name = expression.split(".", 1)[1]
    dot_form = f"echo ${{{{ inputs.{property_name} }}}}"
    bracket_form = f"echo ${{{{ inputs['{property_name}'] }}}}"
    assert expression in _untrusted_references(dot_form)
    assert expression in _untrusted_references(bracket_form)


def test_untrusted_expression_guard_matches_default_and_wrapper_forms() -> None:
    assert _untrusted_references("echo ${{ inputs.repos || 'all' }}") == ["inputs.repos"]
    assert _untrusted_references("const v = '${{ format('{0}', inputs.codex_args) }}';") == [
        "inputs.codex_args"
    ]
    assert _untrusted_references("echo ${{ inputs['repos'] }}") == ["inputs.repos"]
    assert _untrusted_references("${{ format('{{prefix}} {0}', inputs.codex_args) }}") == [
        "inputs.codex_args"
    ]
