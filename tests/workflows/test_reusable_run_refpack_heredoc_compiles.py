"""Static guard: the reference-pack Python heredoc embedded in the reusable
agent-run workflows is valid, compilable Python.

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
"Assemble prompt" step — so every Codex keepalive/fix/conflict/verify run in
that repo aborted, while the correctly-indented Claude sibling succeeded.

Ordinary CI never compiled the heredoc body (it lives as text inside a YAML
``run:`` block), so the break was invisible until runtime. This test closes
that gap: it extracts the ``REFPACK_EOF`` heredoc body from both reusable run
workflows and asserts it compiles.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

REUSABLE_RUN_WORKFLOWS = [
    ".github/workflows/reusable-codex-run.yml",
    ".github/workflows/reusable-claude-run.yml",
]

# Matches `python3 <<'REFPACK_EOF'` or `python3 << 'REFPACK_EOF'` and captures
# the heredoc body up to the closing marker.
_HEREDOC = re.compile(
    r"python3 ?<< ?'REFPACK_EOF'\n(.*?)\n\s*REFPACK_EOF",
    re.S,
)


@pytest.mark.parametrize("workflow_rel", REUSABLE_RUN_WORKFLOWS)
def test_refpack_heredoc_compiles(workflow_rel: str) -> None:
    path = ROOT / workflow_rel
    assert path.exists(), f"missing workflow file: {workflow_rel}"

    src = path.read_text()
    match = _HEREDOC.search(src)
    assert match is not None, (
        f"{workflow_rel}: could not locate the python3 <<'REFPACK_EOF' " "reference-pack heredoc"
    )

    body = textwrap.dedent(match.group(1))
    try:
        compile(body, f"<{workflow_rel}:REFPACK_EOF>", "exec")
    except SyntaxError as exc:  # IndentationError is a SyntaxError subclass
        pytest.fail(
            f"{workflow_rel}: reference-pack heredoc does not compile: "
            f"{type(exc).__name__}: {exc}"
        )
