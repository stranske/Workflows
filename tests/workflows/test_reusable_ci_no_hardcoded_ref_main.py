"""Static guard: ``reusable-10-ci-python.yml`` must not hardcode ``ref: main``
on its Workflows helper checkouts.

Background — why this test exists
=================================
Issue #2346: ``.github/workflows/reusable-10-ci-python.yml`` checked out the
Workflows helper code with a hardcoded ``ref: main`` at four sites. Because of
this, a consumer who pinned the reusable at a tag or SHA
(``uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@<sha>``)
still executed **main-HEAD** helper scripts — so every merge to ``main`` was an
instant, untestable-by-consumers, fleet-wide deploy of the helper layer.

The fix mirrors the proven pattern already used by ``reusable-claude-run.yml``,
``reusable-codex-run.yml`` and ``reusable-cursor-run.yml``: a ``workflows_ref``
``workflow_call`` input (``required: false``, ``default: 'main'``) that the
consumer passes to match the ``@ref`` it pinned the reusable at. The helper
checkouts then resolve to ``${{ inputs.workflows_ref }}`` instead of the literal
``main``. Callers that ride ``@main`` and pass nothing keep the old behaviour
via the default, so the change is backward compatible.

This test closes the regression gap: it asserts (a) no literal ``ref: main``
remains on any line, and (b) every ``actions/checkout`` of ``stranske/Workflows``
resolves its ref through the ``workflows_ref`` input.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_REL = ".github/workflows/reusable-10-ci-python.yml"
WORKFLOW_PATH = ROOT / WORKFLOW_REL

# A checkout step line of the form `        ref: main` (any indentation). The
# input default `default: 'main'` and `ref: ${{ inputs.workflows_ref }}` must
# NOT match. This is the line the issue's deliberate-break gate re-introduces.
_REF_MAIN_LINE = re.compile(r"^\s*ref:\s*main\s*$", re.MULTILINE)


def _load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_no_hardcoded_ref_main() -> None:
    """No helper checkout may pin ``ref: main`` literally."""
    assert WORKFLOW_PATH.exists(), f"missing workflow file: {WORKFLOW_REL}"
    src = WORKFLOW_PATH.read_text(encoding="utf-8")
    offenders = [i + 1 for i, line in enumerate(src.splitlines()) if _REF_MAIN_LINE.match(line)]
    assert not offenders, (
        f"{WORKFLOW_REL}: found hardcoded `ref: main` on line(s) {offenders}. "
        "Use `ref: ${{ inputs.workflows_ref }}` so consumers that pin this "
        "reusable get matching helper code instead of main-HEAD."
    )


def test_workflows_ref_input_declared() -> None:
    """The reusable exposes a backward-compatible ``workflows_ref`` input."""
    data = _load_workflow()
    inputs = (data.get(True) or data.get("on") or {})["workflow_call"]["inputs"]
    assert "workflows_ref" in inputs, "missing `workflows_ref` workflow_call input"
    spec = inputs["workflows_ref"]
    assert spec.get("required") is False, "`workflows_ref` must be optional"
    assert spec.get("default") == "main", "`workflows_ref` must default to main"


def test_workflows_checkouts_use_workflows_ref_input() -> None:
    """Every ``stranske/Workflows`` helper checkout resolves via the input."""
    data = _load_workflow()
    jobs = data.get("jobs", {})
    checked = 0
    for job_name, job in jobs.items():
        for step in job.get("steps", []) or []:
            uses = step.get("uses", "")
            if not uses.startswith("actions/checkout"):
                continue
            with_block = step.get("with", {}) or {}
            if with_block.get("repository") != "stranske/Workflows":
                continue
            ref = str(with_block.get("ref", ""))
            checked += 1
            assert "inputs.workflows_ref" in ref, (
                f"job {job_name!r}: checkout of stranske/Workflows uses "
                f"ref={ref!r}; expected `${{{{ inputs.workflows_ref }}}}`."
            )
    assert checked >= 4, (
        f"expected to inspect the 4 known Workflows helper checkouts, " f"found {checked}"
    )
