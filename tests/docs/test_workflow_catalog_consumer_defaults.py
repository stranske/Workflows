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


def test_keepalive_reporter_docs_require_an_app_owned_writer() -> None:
    guide = _read("docs/WORKFLOW_GUIDE.md")
    checklist = _read("docs/workflow-updates/workflow-checklist.md")

    guide_entry = next(
        line for line in guide.splitlines() if "`agents-keepalive-loop-reporter.yml`" in line
    )
    checklist_entry = next(
        line for line in checklist.splitlines() if "`agents-keepalive-loop-reporter.yml`" in line
    )

    for entry in (guide_entry, checklist_entry):
        assert "KEEPALIVE_APP" in entry
        assert "WORKFLOWS_APP" in entry
        assert "fail" in entry.lower() and "closed" in entry.lower()
        assert "no bespoke App mint" not in entry

    assert guide_entry.count("KEEPALIVE_APP") >= 1
    assert checklist_entry.count("KEEPALIVE_APP") >= 1
