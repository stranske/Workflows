"""Preserve the accepted inline repair and the guard's payload-source contract."""

import pytest
from scripts.langchain import followup_issue_generator as generator


def test_guard_repair_does_not_restore_the_coverage_only_helper():
    """Helper-assisted coverage must not silently replace the accepted inline repair."""
    assert not hasattr(generator, "_blocked_reason_with_source"), (
        "Issue #3956 requires inline source annotation; merge the existing repair "
        "instead of accepting the historical helper-assisted implementation"
    )


@pytest.mark.parametrize("blocked_source", ["original_issue", "codex_log"])
def test_guard_reports_later_payload_source_and_stops_scanning(monkeypatch, blocked_source):
    scanned = []

    def check(text):
        scanned.append(text)
        return {"blocked": text == blocked_source, "reason": "policy violation"}

    monkeypatch.setattr(generator, "check_prompt_injection", check)

    result = generator._guard_payloads(
        verification_text="verification_comment",
        original_issue_text="original_issue",
        codex_log="codex_log",
    )

    assert result == {
        "blocked": True,
        "reason": f"policy violation (source: {blocked_source})",
    }
    expected_scans = ["verification_comment", "original_issue"]
    if blocked_source == "codex_log":
        expected_scans.append("codex_log")
    assert scanned == expected_scans
