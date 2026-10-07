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
    # Replace the whole authored bullet, not just its text: checked criteria
    # must not accidentally become nested "- - [x]" pseudo-items.
    context = context.replace(
        "- " + fixture.ACCEPTANCE_SENTINEL,
        criterion if criterion.startswith("- ") else "- " + criterion,
    ).replace(
        "## PR Diff Summary",
        "## Acceptance evidence\n\n- Overall retrieval status: **present**\n"
        f"- PR body: **{body}**\n- PR comments: **{comments}**\n"
        f"- Referenced workflow artifacts: **{artifacts}**\n{suffix}\n\n## PR Diff Summary",
    )
    return verifier._apply_coverage_floor(
        verifier.EvaluationResult(verdict="PASS", used_llm=True),
        verifier.prompt_coverage(context, None),
    ).verdict


@pytest.mark.parametrize("quote", ["`", '"', "'"])
@pytest.mark.parametrize(
    "destination,channel",
    [("workflow artifacts", "artifacts"), ("PR body", "body"), ("PR comment", "comments")],
)
def test_quoted_review_destination_retains_channel(quote, destination, channel):
    criterion = f"Upload the transcript to the {quote}{destination}{quote}."
    assert verifier._required_evidence_channels(criterion) == {channel}
    assert verdict(criterion) == "CONCERNS"
    assert verdict(criterion, **{channel: "present"}) == "PASS"


@pytest.mark.parametrize("quote", ["`", '"', "'"])
def test_quoted_destination_parser_examples_remain_opaque(quote):
    criterion = f"The parser must recognize {quote}PR comment{quote}."
    assert verifier._required_evidence_channels(criterion) == set()
    independent = criterion + " The reviewer must upload a workflow artifact."
    assert verifier._required_evidence_channels(independent) == {"artifacts"}


@pytest.mark.parametrize("quote", ["`", '"', "'"])
def test_quoted_destination_preserves_common_proof_and_negation(quote):
    criterion = f"CI logs must be provided in a {quote}PR comment{quote}."
    assert verifier._required_evidence_channels(criterion) == {"comments"}
    assert verdict(criterion) == "CONCERNS"
    assert (
        verifier._required_evidence_channels(criterion.replace("must be", "must not be")) == set()
    )


def test_partially_recognized_alternatives_fail_closed():
    criterion = "Evidence must be available in a PR comment or workflow artifacts."
    assert verdict(criterion) == "CONCERNS"


@pytest.mark.parametrize(
    "suffix",
    [
        "; the reviewer must upload a workflow artifact",
        " and the reviewer must attach evidence in a PR comment",
    ],
)
def test_provenance_enforcement_storage_preserves_independent_delivery(suffix):
    criterion = (
        "- [x] Exact-head artifact provenance must remain enforced in workflow artifacts" + suffix
    )
    assert verdict(criterion) == "CONCERNS"


def test_comma_only_and_mixed_lists_are_not_permissive_alternatives():
    for destinations in [
        "a PR comment, a workflow artifact",
        "a PR comment and the PR body, or workflow artifacts",
    ]:
        assert verdict("Provide evidence in " + destinations, comments="present") == "CONCERNS"


@pytest.mark.parametrize("prefix", ["", "- [x] "])
def test_provenance_storage_property_is_not_delivery(prefix):
    criterion = (
        prefix + "Exact-head artifact provenance must remain enforced in workflow artifacts."
    )
    assert verifier._required_evidence_channels(criterion) == set()
    assert verdict(criterion, artifacts="unavailable") == "PASS"


@pytest.mark.parametrize(
    "destinations",
    ["a PR comment, or a workflow artifact", "the PR body, a PR comment, or workflow artifacts"],
)
@pytest.mark.parametrize("channel", ["comments", "artifacts"])
def test_punctuated_explicit_destination_alternatives(destinations, channel):
    criterion = "Provide evidence in " + destinations + "."
    assert verdict(criterion, **{channel: "present"}) == "PASS"
    assert verdict(criterion) == "CONCERNS"


@pytest.mark.parametrize("prefix", ["", "- [ ] ", "- [x] "])
@pytest.mark.parametrize("qualifier", ["", "exact-head ", "workflow ", "CI ", "GitHub Actions "])
def test_artifact_provenance_property_does_not_require_delivery(prefix, qualifier):
    criterion = f"{prefix}Source/template context helpers match and existing {qualifier}artifact provenance remains enforced."
    assert verifier._required_evidence_channels(criterion) == set()
    assert verdict(criterion, artifacts="unavailable") == "PASS"


@pytest.mark.parametrize("prefix", ["", "- [ ] ", "- [x] "])
@pytest.mark.parametrize(
    "form",
    [
        "Provide artifact provenance in a PR comment.",
        "Artifact provenance must be provided in a PR comment.",
    ],
)
def test_provenance_review_delivery_still_requires_comments(prefix, form):
    assert verifier._required_evidence_channels(prefix + form) == {"comments"}
    assert verdict(prefix + form, comments="unavailable") == "CONCERNS"
    assert verdict(prefix + form, comments="present", artifacts="unavailable") == "PASS"


@pytest.mark.parametrize("joiner", ["; ", " and "])
def test_provenance_property_cannot_erase_independent_artifact_delivery(joiner):
    criterion = (
        "- [x] Exact-head artifact provenance remains enforced"
        + joiner
        + "the reviewer must attach a workflow artifact."
    )
    assert verifier._required_evidence_channels(criterion) == {"artifacts"}
    assert verdict(criterion, artifacts="unavailable") == "CONCERNS"
    assert verdict(criterion, artifacts="present") == "PASS"


@pytest.mark.parametrize(
    "form",
    [
        "Do not provide artifact provenance in a PR comment.",
        "Artifact provenance is not supposed to be provided in a PR comment.",
    ],
)
def test_provenance_prohibition_does_not_require_comment(form):
    assert verifier._required_evidence_channels("- [x] " + form) == set()


@pytest.mark.parametrize(
    "destination,channel",
    [("the PR body", "body"), ("a PR comment", "comments"), ("a workflow artifact", "artifacts")],
)
@pytest.mark.parametrize("verb", ["Provide", "Artifact provenance must be provided"])
@pytest.mark.parametrize("state", ["absent", "unavailable"])
def test_provenance_delivery_channel_matrix(destination, channel, verb, state):
    subject = " artifact provenance" if verb == "Provide" else ""
    criterion = f"- [x] {verb}{subject} in {destination}."
    assert verifier._required_evidence_channels(criterion) == {channel}
    assert verdict(criterion, **{channel: state}) == "CONCERNS"
    assert verdict(criterion, **{channel: "present"}) == "PASS"


@pytest.mark.parametrize(
    "governor", ["may", "is not expected to", "is not supposed to", "is no longer required to"]
)
def test_provenance_optional_and_negative_governors_preserve_independent_delivery(governor):
    optional = f"- [x] Artifact provenance {governor} be provided in a PR comment."
    assert verifier._required_evidence_channels(optional) == set()
    combined = optional + " The reviewer must attach a workflow artifact."
    assert verifier._required_evidence_channels(combined) == {"artifacts"}
    assert verdict(combined, artifacts="unavailable") == "CONCERNS"


@pytest.mark.parametrize("order", [False, True])
def test_provenance_property_keeps_separate_reviewer_actor(order):
    parts = [
        "The application enforces workflow artifact provenance",
        "the reviewer must provide evidence in a PR comment",
    ]
    if order:
        parts.reverse()
    criterion = "- [x] " + "; ".join(parts)
    assert verifier._required_evidence_channels(criterion) == {"comments"}
    assert verdict(criterion, comments="unavailable") == "CONCERNS"


@pytest.mark.parametrize("prefix", ["", "[ ] "])
@pytest.mark.parametrize(
    "destinations",
    [
        "in a PR comment or workflow artifact",
        "in either a PR comment or a workflow artifact",
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
