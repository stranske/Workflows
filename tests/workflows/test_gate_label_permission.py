"""Gate labels a deliberate-break PR from a job that can write PR labels and runs no PR-head code.

stranske/Orchestrator#1354 (2026-11-12) and #1382 (2026-11-15): with only `issues: write` effective
(the job log printed Issues: write, PullRequests: read), "Apply runtime acceptance-criteria label"
failed "Resource not accessible by integration". Granting pull-requests write to test-quality would
hand PR-mutation authority to the PR-head code that job runs (review on stranske/Workflows#4688), so
the label step lives in its own job, which holds that scope and checks nothing out.
"""

from pathlib import Path

import pytest
import yaml

LABEL_STEP = "Apply runtime acceptance-criteria label"
FILES = [
    ".github/workflows/pr-00-gate.yml",
    "templates/consumer-repo/.github/workflows/pr-00-gate.yml",
]


def _jobs(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))["jobs"]


@pytest.mark.parametrize("path", FILES)
def test_the_label_job_can_write_pull_requests_and_runs_no_pr_code(path):
    jobs = _jobs(path)
    holders = [
        name
        for name, job in jobs.items()
        if any(step.get("name") == LABEL_STEP for step in job.get("steps") or [])
    ]
    assert holders == ["acceptance-criteria-label"], holders
    job = jobs["acceptance-criteria-label"]
    assert job["permissions"] == {"issues": "write", "pull-requests": "write"}
    assert not any("checkout" in str(step.get("uses", "")) for step in job["steps"])
    assert "test-quality" in job["needs"]
    assert "deliberate_break_marker" in job["if"]
    # A labelling failure must never fail Gate.
    assert "acceptance-criteria-label" not in jobs["summary"]["needs"]


@pytest.mark.parametrize("path", FILES)
def test_test_quality_keeps_pull_requests_read_and_exports_the_marker(path):
    job = _jobs(path)["test-quality"]
    assert job["permissions"]["pull-requests"] == "read"
    assert job["outputs"]["deliberate_break_marker"] == (
        "${{ steps.deliberate_break.outputs.has_marker }}"
    )
    assert any(step.get("id") == "deliberate_break" for step in job["steps"])
