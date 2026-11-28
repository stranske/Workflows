"""`automerge` is written only where a merger reads it.

Consumers: keepalive applies it on tasks-complete and Gate Followups' guarded-merge reads it.
Workflows: no workflow reads it (the local closer merges Workflows' agent PRs), so the root
keepalive loop passes apply_automerge_label=false. docs/ops/LOCAL_LANES.md names both mergers.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _summary_inputs(workflow: Path) -> str:
    for job in yaml.safe_load(workflow.read_text())["jobs"].values():
        for step in job.get("steps", []):
            script = (step.get("with") or {}).get("script", "")
            if "await updateKeepaliveLoopSummary(" in script:
                return script
    raise AssertionError(f"{workflow} does not call updateKeepaliveLoopSummary")


def test_root_keepalive_loop_does_not_write_automerge():
    script = _summary_inputs(ROOT / ".github/workflows/agents-keepalive-loop.yml")
    assert re.search(r"apply_automerge_label:\s*false", script)


def test_consumer_gate_followups_keeps_the_automerge_write_and_its_reader():
    workflow = ROOT / "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml"
    assert "apply_automerge_label" not in _summary_inputs(workflow)  # default true
    jobs = yaml.safe_load(workflow.read_text())["jobs"]
    step = next(
        s
        for s in jobs["guarded-merge"]["steps"]
        if s.get("name") == "Merge labelled agent PRs (guarded)"
    )
    script = step["with"]["script"]
    assert "const label = 'automerge';" in script


def test_no_workflows_workflow_reads_the_automerge_label():
    """The decision above holds only while nothing in Workflows reads the label."""
    readers = []
    for workflow in sorted((ROOT / ".github/workflows").glob("*.yml")):
        text = workflow.read_text()
        for line in text.splitlines():
            # A check-run named `automerge` (reusable-agents-pr-health) is not the label.
            if "check.name" in line:
                continue
            if re.search(r"""['"]automerge['"]""", line):
                readers.append(f"{workflow.name}: {line.strip()}")
    assert readers == []
