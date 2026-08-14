from __future__ import annotations

from dataclasses import dataclass

import pytest
from scripts.langchain.verifier_config import (
    EVAL_FOLLOW_UP_BUDGET_TOKENS,
    EVAL_PAIR_BUDGET_TOKENS,
    EVAL_SCHEMA_REPAIR_BUDGET_TOKENS,
    SchemaRepairPolicy,
    artifact_from_verification_text,
    is_terminal_artifact,
)


def test_verifier_budget_constants_are_positive() -> None:
    assert EVAL_PAIR_BUDGET_TOKENS > 0
    assert EVAL_SCHEMA_REPAIR_BUDGET_TOKENS > 0
    assert EVAL_FOLLOW_UP_BUDGET_TOKENS > 0


@pytest.mark.parametrize("attempts", [0, 1])
def test_schema_repair_policy_accepts_valid_attempt_values(attempts: int) -> None:
    policy = SchemaRepairPolicy(max_attempts=attempts, escalation_threshold=attempts)
    assert policy.max_attempts == attempts
    assert policy.escalation_threshold == attempts


@pytest.mark.parametrize("bad", [0.5, True, False])
def test_schema_repair_policy_rejects_non_integer_max_attempts(bad: object) -> None:
    with pytest.raises(TypeError, match="max_repair_attempts must be an integer"):
        SchemaRepairPolicy(max_attempts=bad, escalation_threshold=0)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [2, -1])
def test_schema_repair_policy_rejects_out_of_range_max_attempts(bad: int) -> None:
    with pytest.raises(ValueError, match="max_repair_attempts must be between"):
        SchemaRepairPolicy(max_attempts=bad, escalation_threshold=0)


@pytest.mark.parametrize("bad", [0.5, True, False])
def test_schema_repair_policy_rejects_non_integer_escalation_threshold(bad: object) -> None:
    with pytest.raises(TypeError, match="max_repair_attempts must be an integer"):
        SchemaRepairPolicy(max_attempts=0, escalation_threshold=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [2, -1])
def test_schema_repair_policy_rejects_out_of_range_escalation_threshold(bad: int) -> None:
    with pytest.raises(ValueError, match="max_repair_attempts must be between"):
        SchemaRepairPolicy(max_attempts=0, escalation_threshold=bad)


def test_schema_repair_policy_decision_table() -> None:
    policy = SchemaRepairPolicy(max_attempts=1, escalation_threshold=1)

    cases = [
        (
            {"repair_attempts_used": 0, "error_stage": None, "has_payload": True},
            "terminal",
        ),
        (
            {"repair_attempts_used": 0, "error_stage": "validation", "has_payload": False},
            "retry",
        ),
        (
            {
                "repair_attempts_used": 1,
                "error_stage": "repair_validation",
                "has_payload": False,
            },
            "escalate",
        ),
        (
            {"repair_attempts_used": 1, "error_stage": "unknown", "has_payload": False},
            "terminal",
        ),
    ]

    for kwargs, expected in cases:
        assert policy.terminal_decision(**kwargs) == expected


def test_is_terminal_artifact_accepts_verdict_payloads() -> None:
    assert is_terminal_artifact({"verdict": "PASS", "repair_attempts_used": 0})
    assert is_terminal_artifact({"verdict": "CONCERNS"})
    assert is_terminal_artifact({"verdict": "FAIL"})


def test_is_terminal_artifact_accepts_comparison_results() -> None:
    verifier_run = {
        "results": [
            {"provider_used": "openai", "verdict": "PASS"},
            {"provider_used": "anthropic", "verdict": "CONCERNS"},
        ],
        "report": "## Provider Comparison Report",
    }

    assert is_terminal_artifact(verifier_run)


def test_is_terminal_artifact_rejects_pending_repair_attempts() -> None:
    assert not is_terminal_artifact(
        {
            "error_stage": "validation",
            "repair_attempts_used": 0,
            "repair_attempts_remaining": 1,
        }
    )
    assert not is_terminal_artifact({"repair_pending": True, "verdict": "FAIL"})


def test_is_terminal_artifact_rejects_missing_verdict_for_followup_disposition() -> None:
    assert not is_terminal_artifact({"disposition": "follow-up-created"})
    assert is_terminal_artifact({"disposition": "follow-up-created", "verdict": "FAIL"})


def test_is_terminal_artifact_accepts_terminal_disposition_json_and_objects() -> None:
    assert is_terminal_artifact(
        '{"disposition": "needs-human-depth-limit", "reason": "Depth limit"}'
    )

    @dataclass
    class Run:
        verdict: str
        repair_attempts_used: int = 0

    assert is_terminal_artifact(Run(verdict="ERROR"))


def test_is_terminal_artifact_rejects_empty_or_partial_values() -> None:
    assert not is_terminal_artifact(None)
    assert not is_terminal_artifact("")
    assert not is_terminal_artifact({"summary": "still parsing"})
    assert not is_terminal_artifact({"results": [{"verdict": "PASS"}, {"summary": "partial"}]})


def test_artifact_from_verification_text_extracts_terminal_verdict() -> None:
    artifact = artifact_from_verification_text(
        "## PR Verification Report\n\n**Verdict:** CONCERNS\n\n### Concerns\n- Missing test."
    )

    assert artifact["verdict"] == "CONCERNS"
    assert is_terminal_artifact(artifact)


def test_artifact_from_verification_text_rejects_pending_repair_report() -> None:
    artifact = artifact_from_verification_text(
        "## PR Verification Report\n\nSchema repair pending; validation retry queued."
    )

    assert artifact["repair_pending"] is True
    assert not is_terminal_artifact(artifact)


def test_artifact_from_verification_text_preserves_pending_repair_with_verdict() -> None:
    artifact = artifact_from_verification_text(
        "## PR Verification Report\n\nVerdict: FAIL\n\nSchema repair pending; validation retry queued."
    )

    assert artifact["verdict"] == "FAIL"
    assert artifact["repair_pending"] is True
    assert not is_terminal_artifact(artifact)


def test_artifact_from_verification_text_preserves_newer_pending_repair_after_old_verdict() -> None:
    artifact = artifact_from_verification_text(
        "## PR Verification Report\n\nVerdict: PASS\n\n"
        "---\n\n"
        "## PR Verification Report\n\nSchema repair pending; validation retry queued."
    )

    assert artifact["verdict"] == "PASS"
    assert artifact["repair_pending"] is True
    assert not is_terminal_artifact(artifact)


def test_artifact_from_verification_text_ignores_older_pending_repair_before_latest_verdict() -> (
    None
):
    artifact = artifact_from_verification_text(
        "## PR Verification Report\n\nSchema repair pending; validation retry queued."
        "\n\n---\n\n"
        "## PR Verification Report\n\nVerdict: PASS"
    )

    assert artifact["verdict"] == "PASS"
    assert artifact.get("repair_pending") is not True
    assert is_terminal_artifact(artifact)


def test_artifact_from_verification_text_ignores_stale_repair_marker_with_verdict() -> None:
    artifact = artifact_from_verification_text(
        "Schema repair pending in an older run.\n\n## PR Verification Report\n\nVerdict: FAIL"
    )

    assert artifact["verdict"] == "FAIL"
    assert artifact.get("repair_pending") is not True
    assert is_terminal_artifact(artifact)


def test_artifact_from_verification_text_rejects_malformed_report_without_verdict() -> None:
    artifact = artifact_from_verification_text(
        "## PR Verification Report\n\nThe verifier output did not include a verdict."
    )

    assert artifact["artifact_family"] == "verifier-report"
    assert "verdict" not in artifact
    assert not is_terminal_artifact(artifact)


def test_artifact_from_verification_text_resolves_provider_table() -> None:
    artifact = artifact_from_verification_text(
        "\n".join(
            [
                "## PR Verification Comparison",
                "| Provider | Model | Verdict | Confidence | Summary |",
                "| --- | --- | --- | --- | --- |",
                "| openai | gpt | PASS | 90% | ok |",
                "| anthropic | claude | FAIL | 70% | gap |",
            ]
        )
    )

    assert artifact["verdict"] == "FAIL"
    assert artifact["raw_present"] is True
    assert is_terminal_artifact(artifact)


def test_artifact_from_verification_text_preserves_json_array_results() -> None:
    artifact = artifact_from_verification_text(
        '[{"provider":"openai","verdict":"PASS"},{"provider":"anthropic","verdict":"CONCERNS"}]'
    )

    assert artifact["artifact_family"] == "verifier-report"
    assert artifact["raw_present"] is True
    assert artifact["results"][1]["verdict"] == "CONCERNS"
    assert is_terminal_artifact(artifact)


def test_artifact_from_verification_text_computes_raw_present_authoritatively() -> None:
    artifact = artifact_from_verification_text('{"verdict":"PASS","raw_present":false}')

    assert artifact["raw_present"] is True
    assert artifact["verdict"] == "PASS"
