"""Archived plan ledger: listed paths and stubs must resolve."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_LEDGER = REPO_ROOT / "docs/archive/ARCHIVE_PLANS.md"
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

ARCHIVED_CANONICAL = [
    "docs/archive/plans/SHORT_TERM_PLAN.md",
    "docs/archive/plans/SHORT_TERM_PLAN_SUMMARY.md",
    "docs/archive/plans/LONG_TERM_PLAN.md",
    "docs/archive/audits/WORKFLOW_AUDIT_2025-12-25.md",
    "docs/archive/audits/WORKFLOW_AUDIT_2026-01-09.md",
    "docs/archive/audits/TEMPLATE_REPO_EVALUATION.md",
]

STUBS = [
    "docs/plans/SHORT_TERM_PLAN.md",
    "docs/plans/SHORT_TERM_PLAN_SUMMARY.md",
    "docs/plans/LONG_TERM_PLAN.md",
    "docs/WORKFLOW_AUDIT_2025-12-25.md",
    "docs/WORKFLOW_AUDIT_2026-01-09.md",
]

ACTIVE_PLANS = [
    "docs/TODO_EXTENDED_AUTOPILOT.md",
    "docs/REVIEW_EXTENDED_AUTOPILOT.md",
]


def _resolve_link(source: Path, target: str) -> Path:
    if target.startswith("http://") or target.startswith("https://"):
        raise AssertionError(f"unexpected external link in ledger: {target}")
    if target.startswith("#"):
        raise AssertionError(f"anchor-only link does not resolve to a file: {target}")
    return (source.parent / target).resolve()


def test_archive_plans_ledger_links_resolve() -> None:
    text = ARCHIVE_LEDGER.read_text(encoding="utf-8")
    archive_links = {
        target for target in MARKDOWN_LINK.findall(text) if target.startswith(("plans/", "audits/"))
    }
    assert archive_links == {
        "plans/SHORT_TERM_PLAN.md",
        "plans/SHORT_TERM_PLAN_SUMMARY.md",
        "plans/LONG_TERM_PLAN.md",
        "audits/WORKFLOW_AUDIT_2025-12-25.md",
        "audits/WORKFLOW_AUDIT_2026-01-09.md",
        "audits/TEMPLATE_REPO_EVALUATION.md",
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


def test_workflow_audit_procedure_resolves_from_archive_ledger() -> None:
    text = ARCHIVE_LEDGER.read_text(encoding="utf-8")
    assert "docs/ci/WORKFLOW_AUDIT_PROCEDURE.md" in text
    path = _resolve_link(ARCHIVE_LEDGER, "../ci/WORKFLOW_AUDIT_PROCEDURE.md")
    assert path.is_file()
