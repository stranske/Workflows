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
    assert "python3 .github/scripts/issue_format.py" in text
    assert "python3 workflows-scripts/.github/scripts/issue_format.py" in consumer_text


def test_format_guard_deduplicates_inflight_optimizer_dispatch() -> None:
    guard = Path(".github/workflows/agents-issue-format-guard.yml").read_text(encoding="utf-8")
    assert "Re-fetch before side effects" in guard
    assert "no completion marker written so later runs can retry" in guard
    assert 'marker="<!-- format-guard:$fingerprint -->"' in guard
    assert '"$trusted_marker" == true && "$has_format_label" == true' in guard
    assert "already routed and in flight; skipping duplicate dispatch" in guard
    consumer = Path(
        "templates/consumer-repo/.github/workflows/agents-issue-format-guard.yml"
    ).read_text(encoding="utf-8")
    assert "no completion marker written so later runs can retry" in consumer
    assert '"$trusted_marker" == true && "$has_format_label" == true' in consumer


def test_format_lease_is_required_and_released_after_failure() -> None:
    guard = Path(".github/workflows/agents-issue-format-guard.yml").read_text(encoding="utf-8")
    consumer_guard = Path(
        "templates/consumer-repo/.github/workflows/agents-issue-format-guard.yml"
    ).read_text(encoding="utf-8")
    for text in (guard, consumer_guard):
        assert "could not acquire agents:format lease" in text
        assert text.index("could not acquire agents:format lease") < text.index(
            "gh workflow run agents-issue-optimizer.yml"
        )
    consumer_optimizer = Path(
        "templates/consumer-repo/.github/workflows/agents-issue-optimizer.yml"
    ).read_text(encoding="utf-8")
    for text in (WORKFLOW_PATH.read_text(encoding="utf-8"), consumer_optimizer):
        assert "Release failed format lease" in text
        assert "failure() && steps.check.outputs.should_run == 'true'" in text
