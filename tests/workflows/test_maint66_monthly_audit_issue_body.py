"""Maint 66 audit issue body: documentation routes must resolve on GitHub."""

from __future__ import annotations

import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

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
    github_routes = {
        target
        for target in MARKDOWN_LINK.findall(body)
        if target.startswith("https://github.com/stranske/Workflows/blob/main/")
    }
    assert github_routes == {
        "https://github.com/stranske/Workflows/blob/main/docs/ci/WORKFLOW_AUDIT_PROCEDURE.md",
        "https://github.com/stranske/Workflows/blob/main/docs/archive/ARCHIVE_PLANS.md#workflow-audit-reports",
    }
    assert "WORKFLOW_AUDIT_2025-12-25.md" not in body

    for target in MARKDOWN_LINK.findall(body):
        if target.startswith("http://") or target.startswith("https://"):
            continue
        if target.startswith("#"):
            continue
        file_target = target.split("#", 1)[0]
        path = REPO_ROOT / file_target
        assert path.is_file(), f"broken audit-issue link: {target!r}"


@pytest.mark.parametrize(("total", "successful", "rate"), [(4, 3, 75), (0, 0, 0), (3, 1, 33)])
def test_rendered_checklist_fields(tmp_path: Path, total: int, successful: int, rate: int) -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["audit"]["steps"]
    script = next(step["run"] for step in steps if step.get("id") == "checklist")
    # Hosted runners are isolated. Give each local or parallel test its own intermediate files.
    script = script.replace("/tmp/audit_", "audit_")
    output = tmp_path / "github-output"
    finding = "A literal `workflow-audit` and $(printf sample) with ${TOTAL_RUNS}"
    env = {
        **os.environ,
        "GITHUB_OUTPUT": str(output),
        "TOTAL_RUNS": str(total),
        "TOTAL_SUCCESS": str(successful),
        "TOTAL_FAILURE": str(total - successful),
        "LOOKBACK": "30",
        "FAILING": finding,
        "WARNING": "None",
        "NOT_RUN": "None",
        "API_GUARD": "All clear",
    }
    before = datetime.now(UTC).replace(microsecond=0)
    subprocess.run(["bash", "-e", "-c", script], env=env, cwd=tmp_path, check=True, timeout=15)
    after = datetime.now(UTC)
    body = output.read_text(encoding="utf-8")
    matches = re.search(r"^\*\*Generated:\*\* (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)$", body, re.M)
    assert matches and before <= datetime.fromisoformat(matches[1]) <= after
    assert any(f"## Monthly Workflow Audit - {point:%B %Y}" in body for point in (before, after))
    assert f"| Success Rate | {rate}% |" in body
    assert finding in body
    assert "Check for issues with label `workflow-audit`" in body
