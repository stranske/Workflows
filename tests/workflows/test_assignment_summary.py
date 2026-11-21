"""Exercise the direct Agents 70 assignment summary as an authored shell step."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[2] / ".github/workflows/reusable-70-orchestrator-main.yml"
)


@pytest.mark.parametrize(
    ("matched", "rendered"),
    [
        ("stranske-automation-bot", "stranske-automation-bot"),
        ("", "_none_"),
        ("`review` 100% $(touch unexpected)", "`review` 100% $(touch unexpected)"),
    ],
    ids=["real-assignment", "empty-assignee", "shell-metacharacters"],
)
def test_direct_assignment_summary_renders_outputs(tmp_path, matched, rendered):
    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    step = workflow["jobs"]["verify-assignment-summary"]["steps"][0]["run"]
    summary = tmp_path / "summary.md"
    message = "Issue #2672 has a valid agent assignee."
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step],
        cwd=tmp_path,
        env={
            **os.environ,
            "GITHUB_STEP_SUMMARY": str(summary),
            "ISSUE_NUMBER": "2672",
            "REPOSITORY": "stranske/Workflows",
            "STATUS": "pass",
            "MATCHED": matched,
            "MESSAGE": message,
        },
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )

    assert summary.read_text(encoding="utf-8") == (
        "## Agent issue verification\n"
        "* Issue: [#2672](https://github.com/stranske/Workflows/issues/2672)\n"
        "* Status: pass\n"
        f"* Matched assignee: {rendered}\n"
    )
    assert result.stdout == f"{message}\n"
    assert not (tmp_path / "unexpected").exists()
