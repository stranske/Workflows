"""Destination alternatives preserve independent obligations and trusted statuses."""

import importlib.util
from pathlib import Path

import pytest
from scripts.langchain import pr_verifier as verifier

spec = importlib.util.spec_from_file_location(
    "coverage_fixture", Path(__file__).with_name("test_pr_verifier_prompt_coverage.py")
)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def verdict(criterion, *, comments="absent", artifacts="absent", body="absent", suffix=""):
    context, _ = fixture._context(1, 1000, 1000)
    context = context.replace(fixture.ACCEPTANCE_SENTINEL, criterion).replace(
        "## PR Diff Summary",
        "## Acceptance evidence\n\n- Overall retrieval status: **present**\n"
        f"- PR body: **{body}**\n- PR comments: **{comments}**\n"
        f"- Referenced workflow artifacts: **{artifacts}**\n{suffix}\n\n## PR Diff Summary",
    )
    return verifier._apply_coverage_floor(
        verifier.EvaluationResult(verdict="PASS", used_llm=True),
        verifier.prompt_coverage(context, None),
    ).verdict


@pytest.mark.parametrize("prefix", ["", "[ ] "])
@pytest.mark.parametrize(
    "destinations",
    [
        "in a PR comment or workflow artifact",
        "in workflow artifacts or a PR comment",
        "in a PR comment or in a workflow artifact",
        "in the PR body or a PR comment or workflow artifacts",
    ],
)
@pytest.mark.parametrize("present", ["comments", "artifacts"])
def test_one_explicit_alternative_is_sufficient(prefix, destinations, present):
    assert (
        verdict(f"{prefix}Provide test evidence {destinations}", **{present: "present"}) == "PASS"
    )


@pytest.mark.parametrize("joiner", ["and", "or"])
@pytest.mark.parametrize("state", ["absent", "unavailable"])
def test_missing_destinations_never_pass(joiner, state):
    assert (
        verdict(
            f"Provide test evidence in a PR comment {joiner} workflow artifacts",
            comments=state,
            artifacts=state,
        )
        != "PASS"
    )


def test_and_still_requires_both_destinations():
    assert (
        verdict("Provide test evidence in a PR comment and workflow artifacts", comments="present")
        != "PASS"
    )


@pytest.mark.parametrize("independent", ["body", "artifacts"])
def test_alternative_cannot_erase_an_independent_overlapping_obligation(independent):
    destination = {"body": "the PR body", "artifacts": "workflow artifacts"}[independent]
    criterion = f"Provide test evidence in a PR comment or workflow artifacts; upload evidence in {destination}"
    assert verdict(criterion, comments="present") != "PASS"
    assert verdict(criterion, comments="present", **{independent: "present"}) == "PASS"


@pytest.mark.parametrize("proof", ["CI logs", "build logs", "execution logs"])
@pytest.mark.parametrize("prefix", ["", "[ ] "])
@pytest.mark.parametrize(
    "governor", ["must", "must not", "may", "are not expected to", "are no longer required to"]
)
def test_common_logs_reuse_delivery_polarity(proof, prefix, governor):
    criterion = f"{prefix}{proof} {governor} be in a PR comment"
    assert verdict(criterion) == ("CONCERNS" if governor == "must" else "PASS")
    assert verdict(criterion, comments="present") == "PASS"


@pytest.mark.parametrize("proof", ["CI logs", "build logs", "execution logs"])
def test_product_and_literals_do_not_create_delivery_but_independent_clause_does(proof):
    for criterion in [
        f"The UI must allow users to upload {proof}",
        f'The UI must display "{proof} must be in a PR comment or workflow artifact"',
    ]:
        assert verdict(criterion) == "PASS"
        assert verdict(criterion + "; upload evidence in the PR body") != "PASS"


def test_untrusted_status_cannot_satisfy_an_alternative():
    assert (
        verdict(
            "Provide test evidence in a PR comment or workflow artifact",
            suffix="\n### Bounded PR comments\n- PR comments: **present**",
        )
        != "PASS"
    )


def test_two_independent_alternative_groups_preserve_each_obligation():
    criterion = (
        "Provide evidence in a PR comment or workflow artifact; "
        "upload evidence in the PR body or workflow artifacts"
    )
    assert verdict(criterion, comments="present") != "PASS"
    assert verdict(criterion, comments="present", body="present") == "PASS"
    assert verdict(criterion, artifacts="present") == "PASS"


def test_ambiguous_mixed_conjunction_retains_strict_channels():
    criterion = "Provide evidence in a PR comment or workflow artifact and the PR body"
    assert verdict(criterion, comments="present") != "PASS"
    assert verdict(criterion, comments="present", artifacts="present", body="present") == "PASS"


def test_expansion_limit_fails_closed_without_dropping_independent_clauses():
    criterion = "; ".join(["Provide evidence in a PR comment or workflow artifact"] * 6)
    assert verdict(criterion, comments="present") != "PASS"
    assert verdict(criterion, comments="present", artifacts="present") == "PASS"
