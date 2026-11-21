import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(".github/workflows/maint-71-auto-fix-integration.yml")
RUN_URL = "https://github.com/stranske/Workflows-Integration-Tests/actions/runs/"

# Workflows #4338 and its later notifier comment #6531834676.
ISSUE_BODY = f"Workflows-Integration-Tests CI run [40998550619]({RUN_URL}40998550619) failed"
FOLLOWUP = (
    "Another failure detected:\n\n## Integration Test Failure\n\n"
    f"| **Run ID** | [41115999467]({RUN_URL}41115999467) |"
)


@pytest.fixture
def job():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["detect-and-fix"]


def test_comment_job_admits_only_owner_notifier_reports(job):
    comment_gate = job["if"].split("github.event_name == 'issue_comment'", 1)[1].split("||")[0]
    assert "github.event.comment.author_association == 'OWNER'" in comment_gate
    assert "startsWith(github.event.comment.body, 'Another failure detected:')" in comment_gate
    assert "!github.event.issue.pull_request" in comment_gate


@pytest.mark.parametrize(
    ("event", "payload", "expected"),
    [
        ("issue_comment", {"comment": {"body": FOLLOWUP}}, "41115999467"),
        ("issue_comment", {"comment": {"body": "### 🏷️ Label Suggestions"}}, ""),
        ("issue_comment", {"comment": {"body": ""}}, ""),
        (
            "issue_comment",
            {"comment": {"body": FOLLOWUP.replace("Workflows-Integration-Tests/", "Workflows/")}},
            "",
        ),
        ("issues", {"action": "opened"}, "40998550619"),
        ("issues", {"action": "reopened"}, "40998550619"),
        ("issues", {"issue": {"body": "No linked integration run"}}, ""),
        ("workflow_dispatch", {"inputs": {"run_id": "41115999467"}}, "41115999467"),
        ("workflow_dispatch", {"inputs": {}}, ""),
        ("workflow_dispatch", {"inputs": {"run_id": "41115999467 extra"}}, ""),
    ],
)
def test_extracts_only_the_event_integration_run(job, tmp_path, event, payload, expected):
    extract = next(step["run"] for step in job["steps"] if step.get("id") == "extract")
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps({"issue": {"body": ISSUE_BODY}, **payload}), encoding="utf-8")
    output_file = tmp_path / "output"
    subprocess.run(
        ["bash", "-e", "-c", extract],
        check=True,
        env={
            "PATH": os.environ["PATH"],
            "GITHUB_EVENT_NAME": event,
            "GITHUB_EVENT_PATH": str(event_file),
            "GITHUB_OUTPUT": str(output_file),
        },
    )
    assert output_file.read_text(encoding="utf-8") == f"run_id={expected}\n"
