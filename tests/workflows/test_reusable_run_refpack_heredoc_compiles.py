"""Static guard: the shared reference-pack action used by reusable agent
runner workflows contains valid, compilable Python.

Background — why this test exists
=================================
Issue #2263: ``.github/workflows/reusable-codex-run.yml`` carried an
``IndentationError`` in the "Validate and materialize reference packs" step.
Inside the ``python3 <<'REFPACK_EOF'`` heredoc the ``if token:`` / ``else:``
block was indented at 16 spaces — a level matching no enclosing block (the
loop body is at 14 spaces, the inner ``if`` body at 18). Python raised
``IndentationError: unindent does not match any outer indentation level``.

The step has no step-level ``if:`` and only short-circuits (via a shell guard)
when ``.github/reference_packs.json`` is absent. Any repo that ships that file
(PAEM does today) ran the broken heredoc and failed the step hard, before the
"Assemble prompt" step.

Ordinary CI never compiled the heredoc body (it lives as text inside a YAML
``run:`` block), so the break was invisible until runtime. This test closes
that gap: it extracts the ``REFPACK_EOF`` heredoc body from the shared action
and asserts both reusable run workflows call that action instead of carrying
their own copy.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

REUSABLE_RUN_WORKFLOWS = [
    ".github/workflows/reusable-codex-run.yml",
    ".github/workflows/reusable-claude-run.yml",
]
REFPACK_ACTION = ".github/actions/agent-reference-packs/action.yml"


def _extract_yaml_run_block(path: Path, step_name: str) -> str:
    lines = path.read_text().splitlines()
    step_index = None
    for index, line in enumerate(lines):
        if line.strip() == f"- name: {step_name}":
            step_index = index
            break
    if step_index is None:
        raise AssertionError(f"{path}: missing step named {step_name!r}")

    next_step_index = len(lines)
    for index in range(step_index + 1, len(lines)):
        if lines[index].lstrip().startswith("- name: "):
            next_step_index = index
            break

    for run_index in range(step_index + 1, next_step_index):
        run_line = lines[run_index]
        if run_line.strip() != "run: |":
            continue

        run_indent = len(run_line) - len(run_line.lstrip(" "))
        content_indent = run_indent + 2
        body: list[str] = []
        for body_line in lines[run_index + 1 : next_step_index]:
            if body_line.strip() and len(body_line) - len(body_line.lstrip(" ")) <= run_indent:
                break
            if body_line.startswith(" " * content_indent):
                body.append(body_line[content_indent:])
            else:
                body.append(body_line.lstrip(" "))
        return "\n".join(body)

    raise AssertionError(f"{path}: missing run block for step {step_name!r}")


def _extract_heredoc(script: str, marker: str) -> str:
    heredoc = re.compile(
        rf"python3 ?<< ?'{re.escape(marker)}'\n(.*?)\n{re.escape(marker)}",
        re.S,
    )
    match = heredoc.search(script)
    assert match is not None, f"could not locate python3 <<'{marker}' heredoc"
    return match.group(1)


def test_shared_refpack_action_heredoc_compiles() -> None:
    path = ROOT / REFPACK_ACTION
    assert path.exists(), f"missing action file: {REFPACK_ACTION}"

    script = _extract_yaml_run_block(path, "Validate and materialize reference packs")
    body = _extract_heredoc(script, "REFPACK_EOF")
    try:
        compile(body, f"<{REFPACK_ACTION}:REFPACK_EOF>", "exec")
    except SyntaxError as exc:  # IndentationError is a SyntaxError subclass
        pytest.fail(
            f"{REFPACK_ACTION}: reference-pack heredoc does not compile: "
            f"{type(exc).__name__}: {exc}"
        )


def test_shared_orchestrator_skill_action_heredoc_compiles() -> None:
    path = ROOT / REFPACK_ACTION
    assert path.exists(), f"missing action file: {REFPACK_ACTION}"

    script = _extract_yaml_run_block(path, "Validate and materialize reference packs")
    body = _extract_heredoc(script, "ORCHSKILL_EOF")
    try:
        compile(body, f"<{REFPACK_ACTION}:ORCHSKILL_EOF>", "exec")
    except SyntaxError as exc:  # IndentationError is a SyntaxError subclass
        pytest.fail(
            f"{REFPACK_ACTION}: Orchestrator skill heredoc does not compile: "
            f"{type(exc).__name__}: {exc}"
        )


@pytest.mark.parametrize("workflow_rel", REUSABLE_RUN_WORKFLOWS)
def test_reusable_runners_use_shared_refpack_action(workflow_rel: str) -> None:
    path = ROOT / workflow_rel
    assert path.exists(), f"missing workflow file: {workflow_rel}"

    src = path.read_text()
    assert src.count("uses: ./.github/actions/agent-reference-packs") == 1
    assert "uses: ./.github/actions/agent-reference-packs" in src
    assert (
        "REFPACK_EOF" not in src
    ), f"{workflow_rel}: reference-pack heredoc should live only in {REFPACK_ACTION}"
    assert (
        "ORCHSKILL_EOF" not in src
    ), f"{workflow_rel}: orchestrator-skill heredoc should live only in {REFPACK_ACTION}"
