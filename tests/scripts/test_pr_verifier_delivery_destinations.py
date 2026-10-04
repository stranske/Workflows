"""Exact canary findings: destination completeness and actionable text output."""

import importlib.util
from pathlib import Path

import pytest
from scripts.langchain import pr_verifier as verifier


@pytest.mark.parametrize("modal", ["must", "shall", "needs to"])
def test_existential_comment_requirement(modal):
    assert verifier._required_evidence_channels(
        f"- [ ] There {modal} be a PR comment with command output"
    ) == {"comments"}


@pytest.mark.parametrize("operation", ["record", "capture", "attach", "generate"])
@pytest.mark.parametrize("actor", ["application", "service"])
def test_product_persistence_does_not_require_review_evidence(operation, actor):
    criterion = f"The {actor} must {operation} transcripts in its database"
    assert verifier._required_evidence_channels("- [ ] " + criterion) == set()
    assert verifier._required_evidence_channels(
        "- [ ] " + criterion + "; leave a PR comment with command output"
    ) == {"comments"}
    assert (
        verifier._required_evidence_channels(
            f"- [ ] The {actor} must {operation} transcripts in the PR"
        )
        != set()
    )


@pytest.mark.parametrize("determiner", ["the", "a", "an"])
def test_reversed_product_fields_allow_determiners(determiner):
    criterion = f"The API response must include links to {determiner} evidence"
    assert verifier._required_evidence_channels("- [ ] " + criterion) == set()
    assert verifier._required_evidence_channels(
        "- [ ] " + criterion + "; record evidence in a PR comment"
    ) == {"comments"}


def test_body_is_its_own_evidence_channel():
    assert verifier._required_evidence_channels(
        "- [ ] Include evidence in both a PR comment and the PR body"
    ) == {"comments", "body"}
    assert verifier._required_evidence_channels(
        "- [ ] Include before/after evidence in the PR body"
    ) == {"body"}
    assert not verifier._required_evidence_is_missing(
        "- PR body: **present**\n- PR comments: **absent**\n"
        "- Referenced workflow artifacts: **absent**",
        {"body"},
    )


@pytest.mark.parametrize(
    "status, verdict", [("present", "PASS"), ("absent", "CONCERNS"), ("unavailable", "CONCERNS")]
)
def test_actual_body_channel_controls_full_coverage_floor(status, verdict):
    spec = importlib.util.spec_from_file_location(
        "body_coverage_fixtures", Path(__file__).with_name("test_pr_verifier_prompt_coverage.py")
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    context, _ = fixture._context(1, 1000, 1000)
    context = context.replace(
        fixture.ACCEPTANCE_SENTINEL, "Include before/after evidence in the PR body"
    )
    context = context.replace(
        "## PR Diff Summary",
        f"## Acceptance evidence\n\n- Overall retrieval status: **absent**\n- PR body: **{status}**\n- PR comments: **absent**\n- Referenced workflow artifacts: **absent**\n\n## PR Diff Summary",
    )
    coverage = verifier.prompt_coverage(context, None)
    result = verifier._apply_coverage_floor(
        verifier.EvaluationResult(verdict="PASS", used_llm=True), coverage
    )
    assert result.verdict == verdict
    assert verifier._required_evidence_is_missing(
        "- PR body: **absent**\n- PR comments: **present**\n"
        "\n### Bounded PR body\n- PR body: **present**",
        {"body"},
    )


@pytest.mark.parametrize("verdict", ["CONCERNS", "FAIL"])
def test_nonpass_text_retains_actionable_concerns_and_raw_detail(verdict):
    result = verifier.EvaluationResult(
        verdict=verdict,
        summary="Short summary",
        concerns=["Missing exact-head witness"],
        raw_content="Detailed model explanation",
        used_llm=True,
    )
    text = verifier._evaluation_output_text(result)
    assert text.startswith(f"Verdict: {verdict}")
    assert "Short summary" in text
    assert "Missing exact-head witness" in text
    assert "Detailed model explanation" in text
