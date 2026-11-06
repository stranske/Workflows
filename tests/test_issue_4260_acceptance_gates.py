"""Issue #4260 acceptance criteria must expose extractable deterministic gates.

Keepalive only runs checkbox backticks that match acceptance_gate.COMMAND_PREFIX
(``pytest …``, ``python -m pytest …``, …). A bare node-id backtick yields 0/0
gates, so the primary and deliberate-break criteria name runnable pytest commands.
The dated Hosted timing criterion stays evidence-based (needs GitHub API + Nov 15).
"""

from __future__ import annotations

from scripts.runner_lib.acceptance_gate import Command, extract_commands

ISSUE_4260_ACCEPTANCE_CRITERIA = """
## Acceptance Criteria
- [ ] `pytest tests/test_ci_python_standard.py::test_coverage_runtime_is_the_primary_runtime` passes in this repo and Template.
- [ ] `pytest tests/test_ci_python_standard.py::test_mismatched_coverage_reference_runtime_fails_alignment` covers the deliberate-break: setting `COVERAGE_REFERENCE_RUNTIME: '3.13'` fails the named alignment check, and reverting makes it pass.
- [ ] On 2026-11-15, the Workflows Gate `python ci / python 3.14` and `python 3.13` jobs are each at most 10 minutes across the five latest successful PR runs.
"""

PRIMARY_GATE = (
    "pytest tests/test_ci_python_standard.py::test_coverage_runtime_is_the_primary_runtime"
)
MISMATCH_GATE = (
    "pytest tests/test_ci_python_standard.py::"
    "test_mismatched_coverage_reference_runtime_fails_alignment"
)


def test_issue_4260_acceptance_exposes_pytest_gates() -> None:
    assert extract_commands(ISSUE_4260_ACCEPTANCE_CRITERIA) == [
        Command(0, PRIMARY_GATE),
        Command(1, MISMATCH_GATE),
    ]


def test_issue_4260_acceptance_ignores_bare_node_id_backticks() -> None:
    """Regression: node-id-only backticks are not deterministic gates."""
    bare = """
## Acceptance Criteria
- [ ] `tests/test_ci_python_standard.py::test_coverage_runtime_is_the_primary_runtime` passes.
- [ ] Setting `COVERAGE_REFERENCE_RUNTIME: '3.13'` causes the named test to fail.
"""
    assert extract_commands(bare) == []
