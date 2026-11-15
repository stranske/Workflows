"""Gate's job that applies the runtime acceptance-criteria label must be able to label a PR.

stranske/Orchestrator#1354 (2026-11-12) and #1382 (2026-11-15): with `pull-requests: read` the step
"Apply runtime acceptance-criteria label" failed "Resource not accessible by integration", which
failed test-quality and with it the whole Gate, on every PR carrying a deliberate-break marker.
"""

from pathlib import Path

import pytest
import yaml

LABEL_STEP = "Apply runtime acceptance-criteria label"


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/pr-00-gate.yml",
        "templates/consumer-repo/.github/workflows/pr-00-gate.yml",
    ],
)
def test_the_job_that_labels_the_pr_can_write_pull_requests(path):
    jobs = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["jobs"]
    holders = [
        name
        for name, job in jobs.items()
        if any(step.get("name") == LABEL_STEP for step in job.get("steps") or [])
    ]
    assert holders, f"{path}: no job runs {LABEL_STEP!r}"
    for name in holders:
        permissions = jobs[name].get("permissions") or {}
        assert permissions.get("pull-requests") == "write", (name, permissions)
        assert permissions.get("issues") == "write", (name, permissions)
