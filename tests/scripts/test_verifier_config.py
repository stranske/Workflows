from __future__ import annotations

from dataclasses import dataclass

from scripts.langchain.verifier_config import (
    EVAL_FOLLOW_UP_BUDGET_TOKENS,
    EVAL_PAIR_BUDGET_TOKENS,
    EVAL_SCHEMA_REPAIR_BUDGET_TOKENS,
    SchemaRepairPolicy,
    is_terminal_artifact,
)


def test_verifier_budget_constants_are_positive() -> None:
    assert EVAL_PAIR_BUDGET_TOKENS > 0
    assert EVAL_SCHEMA_REPAIR_BUDGET_TOKENS > 0
    assert EVAL_FOLLOW_UP_BUDGET_TOKENS > 0


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
