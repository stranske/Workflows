"""Maint 66 audit issue body: documentation routes must resolve on GitHub."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/maint-66-monthly-audit.yml"

MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _extract_audit_heredoc(workflow_text: str) -> str:
    match = re.search(
        r"cat > /tmp/audit_body\.md << 'AUDIT_EOF'\n(.*?)AUDIT_EOF",
        workflow_text,
        re.DOTALL,
    )
    assert match, "audit issue body heredoc not found in maint-66-monthly-audit.yml"
    return match.group(1)


def test_audit_issue_body_documentation_links_resolve() -> None:
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    body = _extract_audit_heredoc(workflow_text)
    assert (
        "https://github.com/stranske/Workflows/blob/main/"
        "docs/ci/WORKFLOW_AUDIT_PROCEDURE.md"
    ) in body
    assert (
        "https://github.com/stranske/Workflows/blob/main/"
        "docs/archive/ARCHIVE_PLANS.md#workflow-audit-reports"
    ) in body
    assert "WORKFLOW_AUDIT_2025-12-25.md" not in body

    for target in MARKDOWN_LINK.findall(body):
        if target.startswith("http://") or target.startswith("https://"):
            continue
        if target.startswith("#"):
            continue
        file_target = target.split("#", 1)[0]
        path = REPO_ROOT / file_target
        assert path.is_file(), f"broken audit-issue link: {target!r}"
