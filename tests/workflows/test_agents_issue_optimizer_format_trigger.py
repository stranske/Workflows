from pathlib import Path

import yaml

WORKFLOW_PATH = Path(".github/workflows/agents-issue-optimizer.yml")


def _load_workflow() -> dict:
    assert WORKFLOW_PATH.exists(), "agents-issue-optimizer.yml must exist"
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_issue_optimizer_triggers_on_labeled_event() -> None:
    workflow = _load_workflow()
    triggers = workflow.get("on") or workflow.get(True) or {}
    issues = triggers.get("issues") or {}
    types = issues.get("types") or []
    assert "labeled" in types


def test_issue_optimizer_checks_for_format_label() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "agents:format" in text
    assert "phase=format" in text


def test_issue_optimizer_validates_format_and_apply_bodies() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "issue_format.py /tmp/formatted_body.md" in text
    assert "issue_format.py /tmp/updated_body.md" in text
    consumer = Path("templates/consumer-repo/.github/workflows/agents-issue-optimizer.yml")
    consumer_text = consumer.read_text(encoding="utf-8")
    assert "issue_format.py /tmp/formatted_body.md" in consumer_text
    assert "issue_format.py /tmp/updated_body.md" in consumer_text


def test_format_guard_retries_incomplete_optimizer_dispatch() -> None:
    guard = Path(".github/workflows/agents-issue-format-guard.yml").read_text(encoding="utf-8")
    assert "Re-fetch before side effects" in guard
    assert "no completion marker written so later runs can retry" in guard
    assert 'marker="<!-- format-guard:$fingerprint -->"' in guard
    consumer = Path(
        "templates/consumer-repo/.github/workflows/agents-issue-format-guard.yml"
    ).read_text(encoding="utf-8")
    assert "no completion marker written so later runs can retry" in consumer
