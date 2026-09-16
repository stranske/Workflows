from __future__ import annotations

from pathlib import Path

CONSUMER_GATE_FOLLOWUPS = Path(
    "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml"
)


def _workflow_text() -> str:
    return CONSUMER_GATE_FOLLOWUPS.read_text(encoding="utf-8")


def _wakeup_script() -> str:
    text = _workflow_text()
    start = text.index("  generated-delivery-wakeup:")
    end = text.index("  guarded-merge:", start)
    job = text[start:end]
    script_start = job.index("script: |") + len("script: |")
    return job[script_start:]


def test_generated_delivery_wakeup_swallows_cross_repo_authorization_errors() -> None:
    script = _wakeup_script()
    assert "[403, 404].includes(status)" in script
    assert "core.warning" in script
    assert "Generated-delivery wakeup skipped" in script
    assert "stranske/Workflows" in script
    assert "WRITE_TOKEN" in script
    # Do not claim success when the dispatch was skipped as unauthorized.
    assert "SKIPPED_UNAUTHORIZED" in script
    assert "outcome !== SKIPPED_UNAUTHORIZED" in script


def test_generated_delivery_wakeup_still_retries_transient_failures() -> None:
    script = _wakeup_script()
    assert "[429, 500, 502, 503, 504].includes(status)" in script
    assert "core.setFailed" in script
    assert "Generated-delivery wakeup failed" in script
    # Non-auth, non-transient statuses must still throw (do not broaden the swallow).
    assert "if (![429, 500, 502, 503, 504].includes(status)) throw error" in script


def test_generated_delivery_wakeup_only_best_effort_create_dispatch() -> None:
    """Audit: only the wakeup job uses createDispatchEvent; other WRITE_TOKEN steps must not."""
    text = _workflow_text()
    assert text.count("createDispatchEvent") == 1
    script = _wakeup_script()
    assert "createDispatchEvent" in script
    # Same-repo WRITE_TOKEN steps (security gate / evaluate / comment / merge) stay fail-hard.
    assert "Security gate - prompt injection guard" in text
    assert "Evaluate workflow_run" in text


def test_generated_delivery_wakeup_deliberate_break_would_fail_auth_swallow() -> None:
    """Deliberate-break gate: removing the 403/404 branch must fail this assertion."""
    script = _wakeup_script()
    assert "Best-effort wakeup" in script
    assert "#3364" in script
    assert "[403, 404].includes(status)" in script
