from pathlib import Path

import yaml

WORKFLOWS = (
    Path(".github/workflows/agents-keepalive-loop.yml"),
    Path("templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml"),
)


def test_keepalive_workflows_transport_task_progress_through_the_runner_cli() -> None:
    # Keep this cohort explicit: the root and consumer workflows must evolve together.
    assert len(WORKFLOWS) == 2
    for path in WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        workflow = yaml.safe_load(text)
        jobs = workflow["jobs"]
        evaluate_outputs = jobs["evaluate"]["outputs"]
        completion = jobs["record-keepalive-completion"]

        assert "task_progress_snapshot" in evaluate_outputs
        assert "summary" in completion["needs"]
        assert "buildTaskProgressSnapshot" in text
        assert '--task-progress-before "$TASK_PROGRESS_BEFORE"' in text
        assert '--observed-head-sha "$OBSERVED_HEAD_SHA"' in text
        assert '--task-progress-after "$TASK_PROGRESS_AFTER"' in text


def test_keepalive_workflows_remain_valid_yaml() -> None:
    for path in WORKFLOWS:
        assert isinstance(yaml.safe_load(path.read_text(encoding="utf-8")), dict)
