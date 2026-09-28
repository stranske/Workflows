import json
import pathlib
import subprocess

import yaml


ROOT = pathlib.Path(__file__).parents[2]
HELPER = ROOT / ".github/scripts/gate-fork-status-publication.js"
WORKFLOW = ROOT / ".github/workflows/pr-00-gate-fork-status.yml"


def _decide(run, jobs, changed_files):
    source = f"""
const helper = require({json.dumps(str(HELPER))});
const result = helper.publicationState({json.dumps({"run": run, "jobs": jobs, "changedFiles": changed_files})});
process.stdout.write(JSON.stringify(result));
"""
    completed = subprocess.run(
        ["node", "-e", source], check=True, capture_output=True, text=True
    )
    return json.loads(completed.stdout)


def test_fork_gate_status_publisher_has_trusted_minimal_permissions():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert data["permissions"] == {
        "actions": "read",
        "contents": "read",
        "pull-requests": "read",
        "statuses": "write",
    }
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "github.event.repository.default_branch" in source
    assert "persist-credentials: false" in source
    assert "pull_request_target" not in source
    helper = HELPER.read_text(encoding="utf-8")
    assert "is not from a fork; the Gate summary remains its status writer" in helper


def test_fork_gate_status_requires_explicit_success_and_complete_summary():
    jobs = [{"name": "summary", "status": "completed", "conclusion": "success"}]
    assert _decide({"status": "completed", "conclusion": "success"}, jobs, ["src/app.py"])["state"] == "success"
    assert _decide({"status": "completed", "conclusion": "neutral"}, jobs, ["src/app.py"])["state"] == "error"
    assert _decide({"status": "completed", "conclusion": "success"}, [], ["src/app.py"])["state"] == "error"


def test_fork_gate_status_blocks_changed_control_surface():
    jobs = [{"name": "summary", "status": "completed", "conclusion": "success"}]
    result = _decide(
        {"status": "completed", "conclusion": "success"},
        jobs,
        [".github/workflows/pr-00-gate.yml"],
    )
    assert result["state"] == "error"
    assert "controls changed" in result["description"]


def test_fork_gate_status_binding_rejects_stale_head_sha():
    source = f"""
const helper = require({json.dumps(str(HELPER))});
try {{
  helper.validateBinding({{
    run: {{event: 'pull_request', name: 'Gate', repository: {{id: 1}}, head_sha: 'old'}},
    workflow: {{path: '.github/workflows/pr-00-gate.yml'}},
    pr: {{base: {{repo: {{id: 1}}}}, head: {{repo: {{id: 2}}, sha: 'new'}}}},
    repository: {{id: 1}},
  }});
  process.exit(2);
}} catch (error) {{
  process.stdout.write(error.message);
}}
"""
    completed = subprocess.run(
        ["node", "-e", source], check=True, capture_output=True, text=True
    )
    assert completed.stdout == "PR head no longer matches Gate head"
