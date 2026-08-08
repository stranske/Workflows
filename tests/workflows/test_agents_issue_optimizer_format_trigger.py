from pathlib import Path

import yaml

WORKFLOW_PATH = Path(".github/workflows/agents-issue-optimizer.yml")
CONSUMER_WORKFLOW_PATH = Path(
    "templates/consumer-repo/.github/workflows/agents-issue-optimizer.yml"
)
GUARD_PATH = Path(".github/workflows/agents-issue-format-guard.yml")
CONSUMER_GUARD_PATH = Path(
    "templates/consumer-repo/.github/workflows/agents-issue-format-guard.yml"
)


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
    consumer_text = CONSUMER_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "python3 .github/scripts/issue_format.py /tmp/formatted_body.md" in text
    assert "python3 .github/scripts/issue_format.py /tmp/updated_body.md" in text
    # Consumer template vendors issue_format.py from the Workflows sparse checkout.
    assert (
        "python workflows-scripts/.github/scripts/issue_format.py /tmp/formatted_body.md"
        in consumer_text
    )
    assert (
        "python workflows-scripts/.github/scripts/issue_format.py /tmp/updated_body.md"
        in consumer_text
    )


def test_format_guard_deduplicates_inflight_optimizer_dispatch() -> None:
    guard = GUARD_PATH.read_text(encoding="utf-8")
    consumer = CONSUMER_GUARD_PATH.read_text(encoding="utf-8")
    for text in (guard, consumer):
        assert "Re-fetch before side effects" in text
        assert "no completion marker written so later runs can retry" in text
        assert 'marker="<!-- format-guard:$fingerprint -->"' in text
        assert "comment.user?.login === 'github-actions[bot]'" in text
        assert "comment.user?.id == null || comment.user.id === 41898282" in text
        assert "createTokenAwareRetry" in text
        assert "paginateWithRetry" in text
        assert "github.rest.issues.listComments" in text
        assert "per_page: 100" in text
        assert "github_token: ${{ github.token }}" in text
        assert "secrets: ${{ toJSON(secrets) }}" not in text
        assert '"$trusted_marker" == true && "$has_format_label" == true' in text
        assert "already routed and in flight; skipping duplicate dispatch" in text
        # Trusted marker is written only after a successful workflow_dispatch.
        assert text.index("gh workflow run agents-issue-optimizer.yml") < text.index(
            'echo "$marker"'
        )


def test_format_lease_is_required_and_released_after_failure() -> None:
    guard = GUARD_PATH.read_text(encoding="utf-8")
    consumer_guard = CONSUMER_GUARD_PATH.read_text(encoding="utf-8")
    for text in (guard, consumer_guard):
        assert "could not acquire agents:format lease" in text
        lease_idx = text.index("could not acquire agents:format lease")
        dispatch_idx = text.index("gh workflow run agents-issue-optimizer.yml")
        assert lease_idx < dispatch_idx
        assert "exit 1" in text[lease_idx:dispatch_idx]
        # Dispatch must stay inside the success path after lease acquisition.
        assert '--add-label "agents:format"' in text[:dispatch_idx]

    for text in (
        WORKFLOW_PATH.read_text(encoding="utf-8"),
        CONSUMER_WORKFLOW_PATH.read_text(encoding="utf-8"),
    ):
        assert "Release failed format lease" in text
        assert (
            "(failure() || cancelled()) && steps.check.outputs.should_run == 'true' "
            "&& steps.check.outputs.phase == 'format'"
        ) in text
        assert 'gh issue edit "$ISSUE_NUMBER" --remove-label "agents:format"' in text
