from __future__ import annotations

import pathlib

WORKFLOW_DIR = pathlib.Path(".github/workflows")
ARCHIVE_LEDGER_PATH = pathlib.Path("docs/archive/ARCHIVE_WORKFLOWS.md")


SUPERSEDED_WORKFLOWS: dict[str, tuple[str, ...]] = {
    "ci.yml": ("pr-00-gate.yml",),
    "docker.yml": ("pr-00-gate.yml",),
    "gate.yml": ("pr-00-gate.yml",),
    "docs-only.yml": ("pr-00-gate.yml",),
    "pr-14-docs-only.yml": ("pr-00-gate.yml",),
    "pr-status-summary.yml": ("pr-00-gate.yml",),
    "ci-matrix-summary.yml": ("pr-00-gate.yml",),
    "check-failure-tracker.yml": ("pr-00-gate.yml",),
    "repo-health-self-check.yml": ("health-40-repo-selfcheck.yml",),
    "repo-health-nightly.yml": ("health-41-repo-health.yml",),
    "ci-signature-guard.yml": ("health-43-ci-signature-guard.yml",),
    "agents-47-verify-codex-bootstrap-matrix.yml": ("agents-70-orchestrator.yml",),
    "assign-to-agents.yml": (
        "agents-63-issue-intake.yml",
        "agents-70-orchestrator.yml",
    ),
}


def test_superseded_workflows_absent_from_inventory() -> None:
    """Legacy wrappers should stay deleted after the archival sweep."""

    lingering = sorted(name for name in SUPERSEDED_WORKFLOWS if (WORKFLOW_DIR / name).exists())
    assert not lingering, f"Superseded workflows resurfaced: {lingering}"


def test_archive_ledger_lists_superseded_workflows() -> None:
    """The archive ledger should enumerate the retired workflows and replacements."""

    ledger_text = ARCHIVE_LEDGER_PATH.read_text(encoding="utf-8")

    for slug, replacements in SUPERSEDED_WORKFLOWS.items():
        assert slug in ledger_text, f"Archive ledger missing entry for {slug}"
        for replacement in replacements:
            assert (
                replacement in ledger_text
            ), f"Archive ledger missing replacement {replacement} for {slug}"
