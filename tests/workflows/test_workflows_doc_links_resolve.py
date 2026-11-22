"""Validate workflow filenames referenced by docs/ci/WORKFLOWS.md exist."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

WORKFLOWS_DOC = Path("docs/ci/WORKFLOWS.md")
# A referenced workflow is valid if it ships in the Workflows repo root or in the
# consumer-repo template. The consumer-default event hub pair
# (agents-80-pr-event-hub.yml, agents-81-gate-followups.yml) lives only in the
# template, so checking the root directory alone reports spurious dangling links.
WORKFLOW_DIRS = (
    Path(".github/workflows"),
    Path("templates/consumer-repo/.github/workflows"),
)
WORKFLOW_LINK_RE = re.compile(r"\]\(\.\./\.\./\.github/workflows/([^)#]+\.yml)(?:#[^)]+)?\)")
BACKTICK_WORKFLOW_RE = re.compile(r"`\.?([A-Za-z0-9][A-Za-z0-9_.-]+\.yml)`")


def _workflow_references() -> list[str]:
    contents = WORKFLOWS_DOC.read_text(encoding="utf-8")
    references = set(WORKFLOW_LINK_RE.findall(contents))

    for candidate in BACKTICK_WORKFLOW_RE.findall(contents):
        if "*" not in candidate and "/" not in candidate:
            references.add(candidate)

    return sorted(references)


def test_workflows_doc_references_existing_workflow_files() -> None:
    references = _workflow_references()
    dangling = [
        name
        for name in references
        if not any((directory / name).is_file() for directory in WORKFLOW_DIRS)
    ]

    print(f"workflow references checked: {len(references)}")
    print(f"dangling workflow references: {dangling}")

    assert references, "docs/ci/WORKFLOWS.md should reference at least one workflow file"
    assert not dangling, f"Dangling workflow reference(s): {dangling}"


def test_bare_validate_workflow_yaml_passes_on_git_changed_workflows() -> None:
    """Acceptance criterion 3: `python scripts/validate_workflow_yaml.py` on PR-touched workflows."""
    result = subprocess.run(
        [sys.executable, "scripts/validate_workflow_yaml.py"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert (
        "validated successfully" in result.stdout
        or "No changed workflow files to validate" in result.stdout
    ), result.stdout


def test_november_2026_archived_workflow_audit_report() -> None:
    """PR #4770 acceptance: archive audit report structure and workflow dispositions."""
    from tests.docs import test_workflow_audit_2026_11_19 as audit_tests

    audit_tests.test_november_2026_audit_report_exists()
    audit_tests.test_november_2026_audit_report_sections()
    audit_tests.test_november_2026_audit_covers_below_50_workflows()
    audit_tests.test_november_2026_audit_covers_50_80_band()
    audit_tests.test_november_2026_audit_records_not_run_inventory()
