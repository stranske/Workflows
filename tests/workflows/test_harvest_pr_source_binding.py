"""Regression tests for recurring verifier-corpus PR source binding."""

import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/maint-79-verifier-corpus-harvest.yml"
SOURCE_CONTEXT = ROOT / ".github/scripts/source_context.js"


def _harvest_body() -> str:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["harvest"]["steps"]
    create_pr = next(
        step for step in steps if step.get("name") == "Open auto-merging corpus-growth PR"
    )
    return create_pr["with"]["body"]


def _extract_issue_numbers(text: str) -> list[int]:
    script = """
const { extractIssueNumbersFromText } = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify([...extractIssueNumbersFromText(input)]));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(SOURCE_CONTEXT), json.dumps(text)],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_harvest_pr_body_yields_no_closing_reference() -> None:
    body = _harvest_body()
    assert "workflow-source:automation_run" in body
    assert "https://github.com/stranske/Workflows/issues/2819" in body
    assert len(_extract_issue_numbers(body)) == 0


def test_owner_repo_hash_reference_is_never_a_closing_reference() -> None:
    assert _extract_issue_numbers("stranske/Workflows#2819") == []
    assert _extract_issue_numbers("stranske/issue-#2819") == []
    assert _extract_issue_numbers("Closes #2819") == [2819]
