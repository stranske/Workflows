#!/usr/bin/env python3
"""Integration tests for verdict policy parity across workflow + follow-up paths."""

from scripts.langchain import followup_issue_generator, verdict_extract
from scripts.langchain.followup_issue_generator import extract_verification_data


def _workflow_result(summary: str):
    return verdict_extract.build_verdict_result(summary, policy="worst")


def _followup_result(summary: str):
    verification_data = extract_verification_data(summary)
    return followup_issue_generator._resolve_verdict_policy(verification_data)


def _build_summary(*rows: str) -> str:
    header = (
        "| Provider | Model | Verdict | Confidence | Summary |\n"
        "| --- | --- | --- | --- | --- |\n"
    )
    body = "\n".join(rows)
    return f"## Provider Summary\n\n{header}{body}\n"


def test_split_verdict_confidence_boundary_needs_human_false():
    summary = _build_summary(
        "| openai | gpt-5.2 | PASS | 0.92 | Looks good. |",
        "| anthropic | claude-sonnet-4-5 | CONCERNS | 0.85 | Missing edge case. |",
    )

    workflow_result = _workflow_result(summary)
    followup_result = _followup_result(summary)

    assert workflow_result.verdict == followup_result.verdict == "CONCERNS"
    assert workflow_result.needs_human is False
    assert followup_result.needs_human is False


def test_split_verdict_low_confidence_needs_human_true():
    summary = _build_summary(
        "| openai | gpt-5.2 | PASS | 0.92 | Looks good. |",
        "| anthropic | claude-sonnet-4-5 | CONCERNS | 0.84 | Missing edge case. |",
    )

    workflow_result = _workflow_result(summary)
    followup_result = _followup_result(summary)

    assert workflow_result.verdict == followup_result.verdict == "CONCERNS"
    assert workflow_result.needs_human is True
    assert followup_result.needs_human is True


def test_split_verdict_row_order_invariance():
    summary_a = _build_summary(
        "| openai | gpt-5.2 | PASS | 0.91 | Looks good. |",
        "| anthropic | claude-sonnet-4-5 | CONCERNS | 0.86 | Missing edge case. |",
    )
    summary_b = _build_summary(
        "| anthropic | claude-sonnet-4-5 | CONCERNS | 0.86 | Missing edge case. |",
        "| openai | gpt-5.2 | PASS | 0.91 | Looks good. |",
    )

    workflow_a = _workflow_result(summary_a)
    workflow_b = _workflow_result(summary_b)
    followup_a = _followup_result(summary_a)
    followup_b = _followup_result(summary_b)

    assert workflow_a.verdict == workflow_b.verdict
    assert workflow_a.needs_human == workflow_b.needs_human
    assert followup_a.verdict == followup_b.verdict
    assert followup_a.needs_human == followup_b.needs_human
