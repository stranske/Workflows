#!/usr/bin/env python3
"""Tests for verdict_policy helpers."""

from scripts.langchain.verdict_policy import (
    CONCERNS_NEEDS_HUMAN_THRESHOLD,
    ProviderVerdict,
    evaluate_verdict_policy,
    extract_provider_verdicts,
    select_verdict,
)


def test_extract_provider_verdicts_from_summary_table():
    summary = """
## Provider Summary

| Provider | Model | Verdict | Confidence | Summary |
| --- | --- | --- | --- | --- |
| openai | gpt-5.2 | PASS | 86% | Looks good. |
| anthropic | claude-sonnet-4-5 | CONCERNS | 85% | Missing edge case. |
"""
    verdicts = extract_provider_verdicts(summary)

    assert len(verdicts) == 2
    assert verdicts[0].provider == "openai"
    assert verdicts[0].model == "gpt-5.2"
    assert verdicts[0].verdict == "PASS"
    assert verdicts[0].confidence == 86
    assert verdicts[1].provider == "anthropic"
    assert verdicts[1].verdict == "CONCERNS"
    assert verdicts[1].confidence == 85


def test_select_verdict_worst_case_policy():
    verdicts = [
        ProviderVerdict("openai", "gpt-5.2", "PASS", 86),
        ProviderVerdict("anthropic", "claude-sonnet-4-5", "CONCERNS", 85),
    ]

    assert select_verdict(verdicts, policy="worst") == "CONCERNS"


def test_select_verdict_majority_policy():
    verdicts = [
        ProviderVerdict("openai", "gpt-5.2", "PASS", 86),
        ProviderVerdict("anthropic", "claude-sonnet-4-5", "PASS", 85),
        ProviderVerdict("github-models", "gpt-4o", "CONCERNS", 65),
    ]

    assert select_verdict(verdicts, policy="majority") == "PASS"


def test_needs_human_threshold_boundary():
    verdicts = [
        ProviderVerdict("openai", "gpt-5.2", "PASS", 0.92),
        ProviderVerdict(
            "anthropic", "claude-sonnet-4-5", "CONCERNS", CONCERNS_NEEDS_HUMAN_THRESHOLD
        ),
    ]

    result = evaluate_verdict_policy(verdicts, policy="worst")

    assert result.needs_human is False


def test_needs_human_true_below_threshold():
    """Concerns below the threshold should trigger needs_human."""
    verdicts = [
        ProviderVerdict("openai", "gpt-5.2", "PASS", 0.92),
        ProviderVerdict("anthropic", "claude-sonnet-4-5", "CONCERNS", 0.40),
    ]

    result = evaluate_verdict_policy(verdicts, policy="worst")

    assert result.needs_human is True
    assert result.split_verdict is True
    assert "low-confidence" in result.needs_human_reason


def test_moderate_confidence_concerns_do_not_block():
    """Regression: 72% concerns in a split verdict should not trigger needs_human.

    Previously CONCERNS_NEEDS_HUMAN_THRESHOLD was 0.85, which caused any
    split verdict with <85% concerns to be flagged.  The lowered threshold
    (0.50) allows moderate-confidence concerns to proceed with automatic
    follow-up creation.
    """
    verdicts = [
        ProviderVerdict("openai", "gpt-5.2", "CONCERNS", 72),
        ProviderVerdict("anthropic", "claude-sonnet-4-5", "PASS", 85),
    ]

    result = evaluate_verdict_policy(verdicts, policy="worst")

    assert result.split_verdict is True
    assert result.needs_human is False
    assert result.verdict == "CONCERNS"
