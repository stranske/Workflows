"""Archived plan ledger: listed paths and stubs must resolve."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_LEDGER = REPO_ROOT / "docs/archive/ARCHIVE_PLANS.md"
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

ARCHIVED_CANONICAL = [
    "docs/archive/plans/SHORT_TERM_PLAN.md",
    "docs/archive/plans/LONG_TERM_PLAN.md",
    "docs/archive/audits/WORKFLOW_AUDIT_2025-12-25.md",
    "docs/archive/audits/WORKFLOW_AUDIT_2026-01-09.md",
    "docs/archive/audits/WORKFLOW_AUDIT_2026-11-19.md",
    "docs/archive/audits/TEMPLATE_REPO_EVALUATION.md",
    "docs/archive/audits/issue-3060-verifier-evidence.md",
]

ARCHIVED_KEEPALIVE = {
    "keepalive/BranchSyncAutomationGaps.md",
    "keepalive/GapAssessment.md",
    "keepalive/ProgressLog.md",
    "keepalive/SyncChecklist.md",
}

STUBS = [
    "docs/plans/SHORT_TERM_PLAN.md",
    "docs/plans/SHORT_TERM_PLAN_SUMMARY.md",
    "docs/plans/LONG_TERM_PLAN.md",
    "docs/WORKFLOW_AUDIT_2025-12-25.md",
    "docs/WORKFLOW_AUDIT_2026-01-09.md",
    "docs/WORKFLOW_AUDIT_2026-11-19.md",
]

ACTIVE_PLANS = [
    "docs/TODO_EXTENDED_AUTOPILOT.md",
    "docs/REVIEW_EXTENDED_AUTOPILOT.md",
]


def _ledger_archive_target(canonical_repo_path: str) -> str:
    """Map ``docs/archive/...`` paths to ledger-relative link targets."""

    prefix = "docs/archive/"
    assert canonical_repo_path.startswith(prefix), canonical_repo_path
    return canonical_repo_path.removeprefix(prefix)


def _expected_ledger_archive_links() -> set[str]:
    """Ledger audit/plan links must stay aligned with ``ARCHIVED_CANONICAL``."""

    return {_ledger_archive_target(path) for path in ARCHIVED_CANONICAL} | set(ARCHIVED_KEEPALIVE)


def _resolve_link(source: Path, target: str) -> Path:
    if target.startswith("http://") or target.startswith("https://"):
        raise AssertionError(f"unexpected external link in ledger: {target}")
    if target.startswith("#"):
        raise AssertionError(f"anchor-only link does not resolve to a file: {target}")
    return (source.parent / target).resolve()


def test_archive_plans_ledger_links_resolve() -> None:
    text = ARCHIVE_LEDGER.read_text(encoding="utf-8")
    archive_links = {
        target
        for target in MARKDOWN_LINK.findall(text)
        if target.startswith(("plans/", "audits/", "keepalive/"))
    }
    expected = _expected_ledger_archive_links()
    assert archive_links == expected
    # Gate test-quality requires a literal expected inventory (check_gate_diff_quality).
    assert expected == {
        "plans/SHORT_TERM_PLAN.md",
        "plans/LONG_TERM_PLAN.md",
        "audits/WORKFLOW_AUDIT_2025-12-25.md",
        "audits/WORKFLOW_AUDIT_2026-01-09.md",
        "audits/WORKFLOW_AUDIT_2026-11-19.md",
        "audits/TEMPLATE_REPO_EVALUATION.md",
        "audits/issue-3060-verifier-evidence.md",
        *ARCHIVED_KEEPALIVE,
    }
    for target in MARKDOWN_LINK.findall(text):
        if target.startswith("#"):
            continue
        path = _resolve_link(ARCHIVE_LEDGER, target)
        assert path.is_file(), f"broken ledger link: {target!r}"


def test_archived_canonical_copies_exist() -> None:
    for relative in ARCHIVED_CANONICAL:
        path = REPO_ROOT / relative
        assert path.is_file(), relative


def test_archived_copies_keep_relative_links_resolvable() -> None:
    for relative in ARCHIVED_CANONICAL:
        source = REPO_ROOT / relative
        for target in MARKDOWN_LINK.findall(source.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            path = _resolve_link(source, target)
            assert path.is_file(), f"broken archived-document link: {relative}: {target!r}"


def test_compatibility_stubs_exist() -> None:
    for relative in STUBS:
        path = REPO_ROOT / relative
        assert path.is_file(), relative
        stub = path.read_text(encoding="utf-8")
        assert "archive" in stub.lower()


def test_extended_autopilot_docs_remain_active() -> None:
    for relative in ACTIVE_PLANS:
        path = REPO_ROOT / relative
        assert path.is_file(), relative
        assert "archived stub" not in path.read_text(encoding="utf-8").lower()


def test_short_term_plan_summary_points_to_archive_ledger_section() -> None:
    stub = REPO_ROOT / "docs/plans/SHORT_TERM_PLAN_SUMMARY.md"
    ledger_path = "../archive/ARCHIVE_PLANS.md"
    section = "historical-short-term-plan-briefing"
    assert f"{ledger_path}#{section}" in MARKDOWN_LINK.findall(stub.read_text(encoding="utf-8"))
    ledger = _resolve_link(stub, ledger_path)
    assert ledger == ARCHIVE_LEDGER
    assert (
        "## Historical short-term plan briefing" in ledger.read_text(encoding="utf-8").splitlines()
    )
    assert not (ledger.parent / "plans/SHORT_TERM_PLAN_SUMMARY.md").exists()


def test_workflow_audit_procedure_resolves_from_archive_ledger() -> None:
    text = ARCHIVE_LEDGER.read_text(encoding="utf-8")
    assert "docs/ci/WORKFLOW_AUDIT_PROCEDURE.md" in text
    path = _resolve_link(ARCHIVE_LEDGER, "../ci/WORKFLOW_AUDIT_PROCEDURE.md")
    assert path.is_file()


def test_operator_guide_links_current_branch_sync_recovery() -> None:
    guide = REPO_ROOT / "docs/agent-automation.md"
    links = MARKDOWN_LINK.findall(guide.read_text(encoding="utf-8"))
    assert "keepalive/SyncChecklist.md" not in links
    for target, heading in (
        ("keepalive/GoalsAndPlumbing.md#9-branch-sync-gate", "## 9. Branch-Sync Gate"),
        (
            "keepalive/Observability_Contract.md#8-orchestrator-contract",
            "## 8) Orchestrator Contract",
        ),
    ):
        assert target in links
        section = _resolve_link(guide, target.split("#")[0]).read_text(encoding="utf-8")
        assert heading in section.splitlines()
