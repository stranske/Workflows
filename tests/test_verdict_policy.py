#!/usr/bin/env python3
"""Tests for verdict_policy helpers."""

import json
import math

import pytest
from scripts.langchain.verdict_policy import (
    CONCERNS_NEEDS_HUMAN_THRESHOLD,
    ProviderVerdict,
    _coerce_confidence,
    _normalize_confidence,
    evaluate_verdict_policy,
    extract_provider_verdicts,
    select_verdict,
)


@pytest.mark.parametrize("raw", ["nan", "NaN", "inf", "INF", "-inf", "1e999", "inf%"])
def test_nonfinite_confidence_text_is_zero(raw):
    assert _coerce_confidence(raw) == 0.0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_confidence_number_is_zero(value):
    assert _normalize_confidence(value) == 0.0


def test_unmarked_confidence_above_one_hundred_is_clamped():
    assert _normalize_confidence(125) == 1.0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("policy", ["worst", "majority"])
def test_nonfinite_concerns_preserve_verdict_without_false_confidence_hold(value, policy):
    verdicts = [
        ProviderVerdict("a", "m1", "pass", 0.9),
        ProviderVerdict("b", "m2", "concerns", value),
    ]
    result = evaluate_verdict_policy(verdicts, policy=policy)
    assert result.verdict_kind == "concerns"
    assert result.split_verdict
    assert result.concerns_confidence == 0.0
    assert result.selected_confidence == 0.0
    assert not result.needs_human
    assert result.providers[1].confidence == 0.0
    if math.isnan(value):
        assert math.isnan(verdicts[1].confidence)
    else:
        assert verdicts[1].confidence == value
    json.dumps(result.as_dict(), allow_nan=False)


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
    assert verdicts[0].confidence == pytest.approx(0.86)
    assert verdicts[1].provider == "anthropic"
    assert verdicts[1].verdict == "CONCERNS"
    assert verdicts[1].confidence == pytest.approx(0.85)


def test_extract_provider_verdicts_preserves_sub_one_percent_unit():
    summary = """
| Provider | Model | Verdict | Confidence |
| --- | --- | --- | --- |
| openai | gpt-5.2 | PASS | 90% |
| anthropic | claude-sonnet-4-5 | CONCERNS | 0.9% |
"""

    verdicts = extract_provider_verdicts(summary)
    result = evaluate_verdict_policy(verdicts)

    assert verdicts[1].confidence == pytest.approx(0.009)
    assert result.concerns_confidence == pytest.approx(0.009)
    assert not result.needs_human


@pytest.mark.parametrize("raw,expected", [("125%", 1.0), ("-10%", 0.0)])
def test_extract_provider_verdicts_clamps_explicit_percent_bounds(raw, expected):
    summary = f"""
| Provider | Model | Verdict | Confidence |
| --- | --- | --- | --- |
| openai | gpt-5.2 | CONCERNS | {raw} |
"""

    verdicts = extract_provider_verdicts(summary)

    assert verdicts[0].confidence == expected


def test_select_verdict_worst_case_policy():
    verdicts = [
        ProviderVerdict("openai", "gpt-5.2", "PASS", 86),
        ProviderVerdict("anthropic", "claude-sonnet-4-5", "CONCERNS", 85),
    ]

    assert select_verdict(verdicts, policy="worst") == "CONCERNS"


def test_select_verdict_worst_case_prefers_fail_over_concerns():
    verdicts = [
        ProviderVerdict("openai", "gpt-5.2", "CONCERNS", 86),
        ProviderVerdict("anthropic", "claude-sonnet-4-5", "FAIL", 85),
    ]

    assert select_verdict(verdicts, policy="worst") == "FAIL"


def test_select_verdict_majority_policy():
    verdicts = [
        ProviderVerdict("openai", "gpt-5.2", "PASS", 86),
        ProviderVerdict("anthropic", "claude-sonnet-4-5", "PASS", 85),
        ProviderVerdict("github-models", "gpt-4o", "CONCERNS", 65),
    ]

    assert select_verdict(verdicts, policy="majority") == "PASS"


def test_needs_human_threshold_boundary():
    """At exactly the threshold, needs_human should fire (>= comparison)."""
    verdicts = [
        ProviderVerdict("openai", "gpt-5.2", "PASS", 0.92),
        ProviderVerdict(
            "anthropic", "claude-sonnet-4-5", "CONCERNS", CONCERNS_NEEDS_HUMAN_THRESHOLD
        ),
    ]

    result = evaluate_verdict_policy(verdicts, policy="worst")

    assert result.needs_human is True


def test_needs_human_true_above_threshold():
    """Concerns above the threshold should trigger needs_human."""
    verdicts = [
        ProviderVerdict("openai", "gpt-5.2", "PASS", 0.92),
        ProviderVerdict("anthropic", "claude-sonnet-4-5", "CONCERNS", 0.90),
    ]

    result = evaluate_verdict_policy(verdicts, policy="worst")

    assert result.needs_human is True
    assert result.split_verdict is True
    assert "high-confidence" in result.needs_human_reason


def test_moderate_confidence_concerns_do_not_block():
    """Moderate-confidence concerns in a split verdict should not trigger needs_human.

    needs_human only fires when the CONCERNS provider is highly confident
    (>= 0.85), indicating the LLM is quite sure there are real problems.
    Moderate confidence means the LLM is uncertain — that's a weaker signal
    and shouldn't block follow-up automation.
    """
    verdicts = [
        ProviderVerdict("openai", "gpt-5.2", "CONCERNS", 72),
        ProviderVerdict("anthropic", "claude-sonnet-4-5", "PASS", 85),
    ]

    result = evaluate_verdict_policy(verdicts, policy="worst")

    assert result.split_verdict is True
    assert result.needs_human is False
    assert result.verdict == "CONCERNS"
