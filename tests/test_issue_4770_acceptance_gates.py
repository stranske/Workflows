"""Issue #4770 acceptance criteria expose the two keepalive deterministic pytest gates."""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

from scripts.runner_lib.acceptance_gate import Command, extract_commands

REPO_ROOT = Path(__file__).resolve().parents[1]

ISSUE_4770_ACCEPTANCE_CRITERIA = """
## Acceptance Criteria

- [ ] `python scripts/check_api_wrapper_guard.py --all` exits with code `0` and zero violations, confirming `.github/scripts/restore_branch_snapshots.py` no longer triggers lines 149 or 194.
- [ ] `pytest tests/scripts/test_issue_dedup.py tests/scripts/test_check_api_wrapper_guard.py tests/workflows/test_maint66_monthly_audit_stats.py tests/workflows/test_maint66_monthly_audit_issue_body.py` passes with zero failures and zero skipped assertions.
- [ ] `pytest tests/scripts/test_validate_workflow_yaml.py tests/workflows/test_workflows_doc_links_resolve.py` pass after all `.github/workflows/*.yml` and `docs/` edits (includes bare `validate_workflow_yaml.py` and archive audit via doc link gate).
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


def _run_gate(command: str) -> subprocess.CompletedProcess[str]:
    argv = shlex.split(command)
    assert argv[0] == "pytest"
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *argv[1:],
            "-q",
            "-m",
            "not slow",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_issue_4770_deterministic_gate_bundles_exit_zero() -> None:
    """Keepalive runs the two extracted pytest gates; both must pass on this branch."""
    for command in (GATE_ISSUE_DEDUP_BUNDLE, GATE_VALIDATE_DOC_BUNDLE):
        result = _run_gate(command)
        assert result.returncode == 0, (command, result.stdout, result.stderr)


def test_issue_4770_acceptance_exposes_two_pytest_gates() -> None:
    assert extract_commands(ISSUE_4770_ACCEPTANCE_CRITERIA) == [
        Command(1, GATE_ISSUE_DEDUP_BUNDLE),
        Command(2, GATE_VALIDATE_DOC_BUNDLE),
    ]


def test_issue_4770_api_wrapper_guard_criterion() -> None:
    """Acceptance criterion 0: check_api_wrapper_guard --all exits 0 with no violations."""
    result = subprocess.run(
        [sys.executable, "scripts/check_api_wrapper_guard.py", "--all"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)


def test_issue_4770_validate_workflow_yaml_criterion() -> None:
    """Acceptance criterion 2: bare validate_workflow_yaml.py on PR-touched workflows."""
    result = subprocess.run(
        [sys.executable, "scripts/validate_workflow_yaml.py"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert (
        "validated successfully" in result.stdout
        or "No changed workflow files to validate" in result.stdout
    ), result.stdout


def test_issue_4770_archived_audit_report_criterion() -> None:
    """Acceptance criterion 3: archive report structure (also exercised in gate 2)."""
    from tests.docs import test_workflow_audit_2026_11_19 as audit_tests

    audit_tests.test_november_2026_audit_report_exists()
    audit_tests.test_november_2026_audit_report_sections()
    audit_tests.test_november_2026_audit_covers_below_50_workflows()
    audit_tests.test_november_2026_audit_covers_50_80_band()
    audit_tests.test_november_2026_audit_records_not_run_inventory()
