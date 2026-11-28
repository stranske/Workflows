"""The archive ledger preserves current and historical navigation."""

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
    "docs/archive/audits/issue-4427-wasm-pytest-handoff.md",
    "docs/archive/audits/issue-4455-post-merge-evidence.md",
]

ARCHIVED_KEEPALIVE = {
    "keepalive/BranchSyncAutomationGaps.md",
    "keepalive/GapAssessment.md",
    "keepalive/Keepalive_Reliability_Plan.md",
    "keepalive/ProgressLog.md",
    "keepalive/SyncChecklist.md",
}

STUBS = [
    "docs/plans/SHORT_TERM_PLAN_SUMMARY.md",
    "docs/WORKFLOW_AUDIT_2026-11-19.md",
]

ORIGINAL_REVISION = "09c73c658d6d4afa2ac5115814087a43fe8bf0d5"
ORIGINAL_ROUTES = {
    "docs/plans/SHORT_TERM_PLAN.md": "january-short-plan-original",
    "docs/plans/LONG_TERM_PLAN.md": "january-long-plan-original",
    "docs/WORKFLOW_AUDIT_2025-12-25.md": "december-audit-original",
    "docs/WORKFLOW_AUDIT_2026-01-09.md": "january-audit-original",
}

# Archived 2026-11-28 when Auto-Pilot was retired (#5379).
ARCHIVED_WITH_AUTOPILOT = {
    "docs/TODO_EXTENDED_AUTOPILOT.md": "docs/archive/plans/TODO_EXTENDED_AUTOPILOT.md",
    "docs/llm-dependencies-audit.md": "docs/archive/audits/llm-dependencies-audit.md",
    "docs/REVIEW_EXTENDED_AUTOPILOT.md": "docs/archive/plans/REVIEW_EXTENDED_AUTOPILOT.md",
}


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
    assert archive_links == {
        "plans/SHORT_TERM_PLAN.md",
        "plans/LONG_TERM_PLAN.md",
        "plans/agent-verifier-v2.md",
        "plans/langchain-issue-intake-proposal.md",
        "plans/langchain-keepalive-integration.md",
        "plans/langchain-rollout-tasks.md",
        "audits/WORKFLOW_AUDIT_2025-12-25.md",
        "audits/WORKFLOW_AUDIT_2026-01-09.md",
        "audits/WORKFLOW_AUDIT_2026-11-19.md",
        "audits/TEMPLATE_REPO_EVALUATION.md",
        "audits/issue-3060-verifier-evidence.md",
        "audits/issue-4427-wasm-pytest-handoff.md",
        "audits/issue-4455-post-merge-evidence.md",
        "audits/february-2026-agent-evaluations.tar.gz",
        *ARCHIVED_KEEPALIVE,
    }
    original_base = f"https://github.com/stranske/Workflows/blob/{ORIGINAL_REVISION}"
    for former_path, reference in ORIGINAL_ROUTES.items():
        assert f"[`{former_path}`][{reference}]" in text
        assert f"[{reference}]: {original_base}/{former_path}" in text.splitlines()

    for target in MARKDOWN_LINK.findall(text):
        if target.startswith("#"):
            continue
        path = _resolve_link(ARCHIVE_LEDGER, target.partition("#")[0])
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
            path = _resolve_link(source, target.partition("#")[0])
            assert path.is_file(), f"broken archived-document link: {relative}: {target!r}"


def test_compatibility_stubs_exist() -> None:
    for relative in STUBS:
        path = REPO_ROOT / relative
        assert path.is_file(), relative
        stub = path.read_text(encoding="utf-8")
        assert "archive" in stub.lower()


def test_auto_pilot_documents_moved_to_archive() -> None:
    ledger = ARCHIVE_LEDGER.read_text(encoding="utf-8")
    for former, archived in ARCHIVED_WITH_AUTOPILOT.items():
        assert not (REPO_ROOT / former).exists(), former
        assert (REPO_ROOT / archived).is_file(), archived
        assert archived in ledger and former in ledger


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
    links = MARKDOWN_LINK.findall(path.read_text(encoding="utf-8"))
    for audit in ("WORKFLOW_AUDIT_2025-12-25.md", "WORKFLOW_AUDIT_2026-01-09.md"):
        target = f"../archive/audits/{audit}"
        assert target in links
        assert _resolve_link(path, target).is_file()


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
