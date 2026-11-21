"""Issue #4770 acceptance criteria expose the two keepalive deterministic pytest gates."""

from __future__ import annotations

from scripts.runner_lib.acceptance_gate import Command, extract_commands

ISSUE_4770_ACCEPTANCE_CRITERIA = """
## Acceptance Criteria

- [ ] `python scripts/check_api_wrapper_guard.py --all` exits with code `0` and zero violations, confirming `.github/scripts/restore_branch_snapshots.py` no longer triggers lines 149 or 194.
- [ ] `pytest tests/scripts/test_issue_dedup.py tests/scripts/test_check_api_wrapper_guard.py tests/workflows/test_maint66_monthly_audit_stats.py tests/workflows/test_maint66_monthly_audit_issue_body.py` passes with zero failures and zero skipped assertions.
- [ ] `python scripts/validate_workflow_yaml.py` and `pytest tests/scripts/test_validate_workflow_yaml.py tests/workflows/test_workflows_doc_links_resolve.py` pass after all `.github/workflows/*.yml` and `docs/` edits.
- [ ] `docs/archive/audits/WORKFLOW_AUDIT_2026-11-19.md` exists and records dispositions for every non-dynamic workflow below 50% success, the 50-80% band, the unrun workflow classification, parallelism/runtime/caching findings, and whether `docs/LABELS.md`, `docs/WORKFLOW_GUIDE.md`, or consumer-sync updates were required.
"""

GATE_ISSUE_DEDUP_BUNDLE = (
    "pytest tests/scripts/test_issue_dedup.py tests/scripts/test_check_api_wrapper_guard.py "
    "tests/workflows/test_maint66_monthly_audit_stats.py "
    "tests/workflows/test_maint66_monthly_audit_issue_body.py"
)
GATE_VALIDATE_DOC_BUNDLE = (
    "pytest tests/scripts/test_validate_workflow_yaml.py "
    "tests/workflows/test_workflows_doc_links_resolve.py"
)


def test_issue_4770_acceptance_exposes_two_pytest_gates() -> None:
    assert extract_commands(ISSUE_4770_ACCEPTANCE_CRITERIA) == [
        Command(1, GATE_ISSUE_DEDUP_BUNDLE),
        Command(2, GATE_VALIDATE_DOC_BUNDLE),
    ]
