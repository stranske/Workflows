from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_workflow_guide_marks_pr_meta_v4_as_workflows_local() -> None:
    content = _read("docs/WORKFLOW_GUIDE.md")

    assert "agents-pr-meta-v4.yml" in content
    assert "Workflows-local" in content
    assert "agents-80-pr-event-hub.yml" in content
    assert "agents-81-gate-followups.yml" in content


def test_ci_workflows_guide_marks_consumer_default_event_hub_pair() -> None:
    content = _read("docs/ci/WORKFLOWS.md")

    assert "agents-pr-meta-v4.yml" in content
    assert "Workflows-repo service workflow" in content
    assert "agents-80-pr-event-hub.yml" in content
    assert "agents-81-gate-followups.yml" in content
