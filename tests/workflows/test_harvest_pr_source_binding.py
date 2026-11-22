"""Regression tests for recurring verifier-corpus PR source binding."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/maint-79-verifier-corpus-harvest.yml"
SOURCE_CONTEXT = ROOT / ".github/scripts/source_context.js"


def _harvest_steps():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["harvest"]["steps"]


def _harvest_body() -> str:
    steps = _harvest_steps()
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


@pytest.mark.parametrize(
    ("event", "write", "expected_args"),
    [
        ("schedule", "", "-m tools.harvest_verifier_corpus --write"),
        ("workflow_dispatch", "false", "-m tools.harvest_verifier_corpus"),
    ],
    ids=["scheduled-write", "manual-preview"],
)
@pytest.mark.parametrize(
    ("status", "message"),
    [
        (17, "harvester fixture interrupted"),
        (0, "harvest: 5 records → 0 promoted (corpus 7→7), 5 staged (FYI, auto-expiring)."),
        (0, "harvest: 0 records → 0 promoted (corpus 7→7), 0 staged (FYI, auto-expiring)."),
    ],
    ids=["failure", "staging", "no-change"],
)
def test_harvest_step_preserves_status_and_summary(
    tmp_path, event, write, expected_args, status, message
):
    step = next(
        item for item in _harvest_steps() if item.get("name") == "Harvest realized-outcome cases"
    )
    program = (
        step["run"].replace("${{ github.event_name }}", event).replace("${{ inputs.write }}", write)
    )
    helper = tmp_path / "python"
    helper.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" > helper-args.txt\n'
        'printf "%s\\n" "$HELPER_MESSAGE"\nexit "$HELPER_STATUS"\n'
    )
    helper.chmod(0o755)
    summary = tmp_path / "summary.md"

    complete = subprocess.run(
        ["bash", "-e", "-c", program],
        cwd=tmp_path,
        env={
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "GITHUB_STEP_SUMMARY": str(summary),
            "HELPER_MESSAGE": message,
            "HELPER_STATUS": str(status),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert complete.returncode == status
    assert (tmp_path / "helper-args.txt").read_text() == expected_args + "\n"
    assert (tmp_path / "harvest.log").read_text() == message + "\n"
    assert message in complete.stdout
    failure = "\nHarvest failed (exit 17).\n\n" if status == 17 else ""
    assert summary.read_text() == f"## Verifier corpus harvest\n{failure}```\n{message}\n```\n"
