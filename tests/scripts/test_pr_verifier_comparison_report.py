import scripts.langchain.pr_verifier as pr_verifier


def test_format_comparison_report_includes_sections() -> None:
    result_a = pr_verifier.EvaluationResult(
        verdict="PASS",
        confidence=0.8,
        scores=pr_verifier.EvaluationScores(
            correctness=8,
            completeness=8,
            quality=8,
            testing=7,
            risks=6,
        ),
        concerns=["Missing tests"],
        summary="Looks good overall.",
        provider_used="github-models",
        used_llm=True,
    )
    result_b = pr_verifier.EvaluationResult(
        verdict="CONCERNS",
        confidence=0.6,
        scores=pr_verifier.EvaluationScores(
            correctness=8,
            completeness=7,
            quality=5,
            testing=6,
            risks=6,
        ),
        concerns=["Missing tests", "Edge case in handler"],
        summary="Needs follow-up on edge cases.",
        provider_used="openai",
        used_llm=True,
    )

    report = pr_verifier.format_comparison_report([result_a, result_b])

    assert "## Provider Comparison Report" in report
    assert "| Provider | Verdict | Confidence | Summary |" in report
    assert "### Agreement" in report
    assert "Concern: Missing tests" in report
    assert "### Disagreement" in report
    assert "| Verdict | PASS | CONCERNS |" in report
    assert "| Quality | 8.0/10 | 5.0/10 |" in report
    assert "### Unique Insights" in report
    assert "- openai: Edge case in handler" in report
    assert "80%" in report


def test_format_comparison_report_single_provider_note() -> None:
    result = pr_verifier.EvaluationResult(
        verdict="PASS",
        confidence=0.9,
        scores=pr_verifier.EvaluationScores(
            correctness=9,
            completeness=9,
            quality=9,
            testing=9,
            risks=8,
        ),
        concerns=[],
        summary="All checks passed.",
        provider_used="github-models",
        used_llm=True,
    )

    report = pr_verifier.format_comparison_report([result])

    assert "Only one provider was available; comparison skipped." in report
