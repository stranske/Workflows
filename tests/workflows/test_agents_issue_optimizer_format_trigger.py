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
        assert "format_guard_attempts" in text
        assert "max_format_guard_attempts=3" in text
        assert "format_guard_next_attempt=$((format_guard_attempts + 1))" in text
        assert "FORMAT_GUARD_RETRY_PREFIX" in text
        assert "isCurrentAttemptMarker" in text
        assert ".displayTitle | endswith($issue)" in text
        assert ".displayTitle | contains($issue)" not in text
        assert "agents:auto-pilot-pause" in text
        assert "Automated formatting stopped after" in text
        assert "<!-- format-guard:attempt-cap -->" in text
        assert text.index("max_format_guard_attempts=3") < text.index(
            "gh workflow run agents-issue-optimizer.yml"
        )
        assert text.index('"$format_guard_attempts" -ge "$max_format_guard_attempts"') < text.index(
            "gh workflow run agents-issue-optimizer.yml"
        )
        assert "github_token: ${{ github.token }}" in text
        assert "secrets: ${{ toJSON(secrets) }}" not in text
        assert '"$trusted_marker" == true && "$has_format_label" == true' in text
        assert "already routed and in flight; skipping duplicate dispatch" in text
        # Every accepted dispatch records a distinct marker, so a retry after the
        # format lease is released still consumes the bounded retry budget.
        assert text.index("gh workflow run agents-issue-optimizer.yml") < text.index(
            'echo "$attempt_marker"'
        )


def test_format_guard_attempt_marker_sequence_consumes_retry_budget() -> None:
    """Exercise the marker contract used by the workflow's routing step."""
    fingerprint = "abc123def456"
    marker = f"<!-- format-guard:{fingerprint} -->"
    retry_prefix = f"<!-- format-guard:{fingerprint}:attempt:"

    def count_accepted_attempts(comments: list[tuple[str, str]]) -> int:
        return sum(
            author == "github-actions[bot]" and (marker in body or retry_prefix in body)
            for author, body in comments
        )

    comments = [("github-actions[bot]", marker)]
    assert count_accepted_attempts(comments) == 1
    comments.append(("github-actions[bot]", f"{retry_prefix}2 -->"))
    comments.append(("github-actions[bot]", f"{retry_prefix}3 -->"))
    comments.append(("outside-user", f"{retry_prefix}4 -->"))
    assert count_accepted_attempts(comments) == 3


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
        # Clock capture precedes the dispatch so an accepted-but-errored CLI can be
        # reconciled; lease release stays inside the failure block only after that probe.
        failure_start = text.index("if ! gh workflow run agents-issue-optimizer.yml")
        assert "dispatch_attempted_at=" in text[dispatch_idx - 200 : failure_start]
        failure_end = text.index("\n          fi", failure_start)
        failure_block = text[failure_start:failure_end]
        assert "preserving agents:format lease" in failure_block
        assert '--remove-label "agents:format"' in failure_block
        assert '|| echo "::warning::could not release failed agents:format lease"' in failure_block
        assert "recorded the accepted attempt for the retry cap" in failure_block

    for text in (
        WORKFLOW_PATH.read_text(encoding="utf-8"),
        CONSUMER_WORKFLOW_PATH.read_text(encoding="utf-8"),
    ):
        assert "Release failed format lease" in text
        assert "(failure() || cancelled())" in text
        assert "steps.check.outputs.phase == 'format'" in text
        assert "github.event.inputs.phase == 'format'" in text
        assert "github.event.label.name == 'agents:format'" in text
        assert 'gh issue edit "$ISSUE_NUMBER" --remove-label "agents:format"' in text


def test_format_guard_uses_event_inputs_and_fails_closed_on_revalidation_errors() -> None:
    for text in (
        GUARD_PATH.read_text(encoding="utf-8"),
        CONSUMER_GUARD_PATH.read_text(encoding="utf-8"),
    ):
        assert "github.event.inputs.issue_number ||\n    github.run_id" in text
        assert "github.event.issue.number || github.event.inputs.issue_number" in text
        assert "revalidate_rc=$?" in text
        assert (
            'python3 .github/scripts/issue_format.py body.md > report.md 2> "$error_file"' in text
        )
        # Exit 0: live body now conforms — skip optimizer dispatch.
        assert 'if [[ "$revalidate_rc" -eq 0 ]]; then' in text
        assert "Live body now conforms — skipping optimizer dispatch." in text
        # Exit 1 + stderr: validator crash — fail closed before fingerprint/dispatch.
        assert 'if [[ "$revalidate_rc" -eq 1 && -s "$error_file" ]]; then' in text
        assert "::error::issue-format validator failed unexpectedly during revalidation" in text
        # Other non-zero: propagate; exit 1 with empty stderr continues to fingerprint.
        assert 'if [[ "$revalidate_rc" -ne 1 ]]; then' in text
        assert 'fingerprint="$(sha256sum body.md | cut -c1-12)"' in text

    for text in (
        WORKFLOW_PATH.read_text(encoding="utf-8"),
        CONSUMER_WORKFLOW_PATH.read_text(encoding="utf-8"),
    ):
        assert (
            "github.event.issue.number || github.event.inputs.issue_number || github.run_id" in text
        )


def test_format_guard_revalidates_before_clearing_state_and_skips_closed_issues() -> None:
    for text in (
        GUARD_PATH.read_text(encoding="utf-8"),
        CONSUMER_GUARD_PATH.read_text(encoding="utf-8"),
    ):
        resolve_idx = text.index("- name: Resolve issue")
        setup_idx = text.index("- name: Setup API client")
        assert resolve_idx < setup_idx
        assert (
            "steps.issue.outputs.exempt != 'true' && steps.issue.outputs.held != 'true'"
            in text[setup_idx : setup_idx + 250]
        )
        invalidate_idx = text.index("- name: Invalidate stale format completion")
        route_idx = text.index("- name: Route non-conforming issue to the optimizer")
        invalidate = text[invalidate_idx:route_idx]
        assert "steps.issue.outputs.state == 'OPEN'" in invalidate
        assert "Live body now conforms — preserving agents:formatted." in invalidate
        assert "validator failed unexpectedly during label revalidation" in invalidate
        route = text[route_idx:]
        assert "steps.issue.outputs.state == 'OPEN'" in route
        assert "Issue is now closed — skipping optimizer dispatch." in route
