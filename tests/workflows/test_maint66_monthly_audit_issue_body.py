"""Maint 66 audit issue body: documentation routes must resolve on GitHub."""

from __future__ import annotations

import os
import re
import subprocess
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
        "AUDIT_MONTH": "November 2026",
        "GENERATED_AT": "2026-11-30T23:59:59Z",
        "TOTAL_RUNS": str(total),
        "TOTAL_SUCCESS": str(successful),
        "TOTAL_FAILURE": str(total - successful),
        "LOOKBACK": "30",
        "FAILING": finding,
        "WARNING": "None",
        "NOT_RUN": "None",
        "API_GUARD": "All clear",
    }
    subprocess.run(["bash", "-e", "-c", script], env=env, cwd=tmp_path, check=True, timeout=15)
    body = output.read_text(encoding="utf-8")
    assert "**Generated:** 2026-11-30T23:59:59Z" in body
    assert "## Monthly Workflow Audit - November 2026" in body
    assert f"| Success Rate | {rate}% |" in body
    assert finding in body
    assert "Check for issues with label `workflow-audit`" in body


def test_issue_title_uses_the_checklist_month_after_midnight(tmp_path: Path) -> None:
    steps = yaml.safe_load(WORKFLOW_PATH.read_text())["jobs"]["audit"]["steps"]
    checklist = next(step for step in steps if step.get("id") == "checklist")
    writer = next(step for step in steps if step["name"] == "Create or update audit issue")
    assert writer["env"]["AUDIT_MONTH"] == checklist["env"]["AUDIT_MONTH"]
    assert writer["env"]["AUDIT_MONTH"] == "${{ steps.stats.outputs.audit_month }}"
    assert checklist["env"]["GENERATED_AT"] == "${{ steps.stats.outputs.generated_at }}"

    # The collection finished in November and the issue is posted after midnight.
    shell = """
date() { echo 'December 2026'; }
gh() {
  if [[ "$2" == create ]]; then printf '%s\\n' "$@" > issue-args; fi
}
"""
    script = writer["run"].replace("${{ github.repository }}", "stranske/Workflows")
    subprocess.run(
        ["bash", "-c", shell + script],
        cwd=tmp_path,
        env={**os.environ, "AUDIT_MONTH": "November 2026", "AUDIT_BODY": "checklist"},
        check=True,
        timeout=15,
    )
    args = (tmp_path / "issue-args").read_text().splitlines()
    assert (
        args[args.index("--title") + 1] == "[Monthly Audit] Workflow Health Check - November 2026"
    )
