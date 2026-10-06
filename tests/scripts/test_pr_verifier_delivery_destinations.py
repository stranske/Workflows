"""Exact canary findings: destination completeness and actionable text output."""

import importlib.util
from itertools import permutations
from pathlib import Path

import pytest
from scripts import docs_drift_fix_agent as fix_agent
from scripts.langchain import pr_verifier as verifier


@pytest.mark.parametrize("role", ["maintainer", "release reviewer"])
@pytest.mark.parametrize("modal", ["may", "can", "could", "would", "should"])
@pytest.mark.parametrize(
    "governor,operation",
    [
        ("must", "place"),
        ("will", "place"),
        ("must have", "placed"),
        ("has", "placed"),
        ("is", "placing"),
        ("needs to", "place"),
    ],
)
@pytest.mark.parametrize(
    "destinations", list(permutations(["the PR body", "a PR comment", "workflow artifacts"], 2))
)
def test_optional_predicate_cannot_suppress_named_actor_delivery(
    role, modal, governor, operation, destinations
):
    """Retain independently governed deliveries across optional actor clauses."""
    before, after = destinations
    expected = "body" if "body" in after else "comments" if "comment" in after else "artifacts"
    first = f"The reviewer {modal} put evidence in {before}"
    second = f"the {role} {governor} {operation} evidence in {after}"
    assert verifier._required_evidence_channels(first + " and " + second) == {expected}
    assert verifier._required_evidence_channels(first + "; " + second) == {expected}
    negative = second.replace(
        governor,
        governor.replace(" have", "") + " not" + (" have" if " have" in governor else ""),
        1,
    )
    assert verifier._required_evidence_channels(first + " and " + negative) == set()
    assert verifier._required_evidence_is_missing(
        "- Overall retrieval status: **absent**\n- PR body: **absent**\n- PR comments: **absent**\n- Referenced workflow artifacts: **absent**",
        verifier._required_evidence_channels(first + " and " + second),
    )


@pytest.mark.parametrize("boundary", ["! ", "? ", ". ", " while ", " and ", "; "])
@pytest.mark.parametrize("predicate", ["must place", "placed", "has placed"])
def test_optional_actor_sentence_boundaries_retain_delivery(boundary, predicate):
    """Sentence and finite-past actor boundaries cannot erase a delivery."""
    criterion = (
        "The reviewer may put evidence in workflow artifacts"
        + boundary
        + f"the maintainer {predicate} evidence in a PR comment"
    )
    assert verifier._required_evidence_channels(criterion) == {"comments"}
    assert verifier._required_evidence_is_missing("- PR comments: **absent**", {"comments"})


@pytest.mark.parametrize(
    "predicate", ["must supply", "must be supplied", "supplied", "is supplying"]
)
@pytest.mark.parametrize(
    "destination,channel",
    [("the PR body", "body"), ("a PR comment", "comments"), ("workflow artifacts", "artifacts")],
)
def test_supply_alias_retains_delivery_and_product_controls(predicate, destination, channel):
    """Supply aliases share obligation, destination, and product semantics."""
    subject = "Test evidence" if "be supplied" in predicate else "The reviewer"
    obj = "" if "be supplied" in predicate else " test evidence"
    criterion = f"{subject} {predicate}{obj} in {destination}"
    assert verifier._required_evidence_channels(criterion) == {channel}
    assert (
        verifier._required_evidence_channels("The service must supply command output to its users")
        == set()
    )
    assert (
        verifier._required_evidence_channels(
            f"The reviewer must not supply evidence in {destination}"
        )
        == set()
    )


def test_optional_actor_cannot_suppress_prove_delivery():
    """Keep the existing prove operation in the shared actor grammar."""
    assert verifier._required_evidence_channels(
        "The reviewer may record evidence in the PR body and the maintainer must prove the result in workflow artifacts"
    ) == {"artifacts"}


@pytest.mark.parametrize(
    "modifier", ["previously published", "already uploaded", "recently recorded"]
)
def test_optional_participial_object_is_not_a_finite_past_actor(modifier):
    """A coordinated evidence modifier has no independently governing actor."""
    criterion = (
        "The reviewer may include current evidence in the PR body and "
        + modifier
        + " evidence in workflow artifacts"
    )
    assert verifier._required_evidence_channels(criterion) == set()


@pytest.mark.parametrize("predicate", ["may inspect", "may check", "must inspect"])
@pytest.mark.parametrize("object_name", ["power supply evidence", "water supply evidence"])
def test_supply_noun_is_not_a_delivery_predicate(predicate, object_name):
    """Object noun supply cannot invent a record operation."""
    assert verifier._required_evidence_channels(
        f"The reviewer {predicate} {object_name} in the PR body"
    ) == ({"overall"} if predicate == "must inspect" else set())


@pytest.mark.parametrize(
    "criterion",
    [
        "The PR comment has to contain command output",
        "The PR comments have to contain command output",
        "Command output has to be in a PR comment",
        "Command outputs have to be in a PR comment",
    ],
)
def test_comment_has_to_uses_shared_mandatory_auxiliary(criterion):
    """Comment requirements reuse the complete mandatory auxiliary vocabulary."""
    assert verifier._required_evidence_channels(criterion) == {"comments"}


@pytest.mark.parametrize("predicate", ["checks", "inspects", "reviews"])
@pytest.mark.parametrize("compound", ["service", "API", "reviewer"])
@pytest.mark.parametrize("alias", ["supply", "supplied", "placed", "submitted", "delivered"])
def test_actor_word_in_supply_object_is_not_clause_subject(predicate, compound, alias):
    """An object compound cannot create a delivery predicate."""
    assert (
        verifier._required_evidence_channels(
            f"The reviewer {predicate} the {compound} {alias} evidence in the PR body"
        )
        == set()
    )


@pytest.mark.parametrize("boundary", [" and ", " while ", ". ", "! ", "? "])
@pytest.mark.parametrize("verb", ["supplies", "records", "provides", "places", "proves"])
def test_optional_actor_cannot_suppress_finite_present_delivery(boundary, verb):
    """An independent finite-present subject cannot inherit optional delivery."""
    assert verifier._required_evidence_channels(
        "The reviewer may supply evidence in the PR body"
        + boundary
        + f"the maintainer {verb} evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize("boundary", [" and ", " while ", ". ", "! ", "? "])
@pytest.mark.parametrize(
    "negation",
    ["does not", "do not", "did not", "does never", "doesn't", "does no longer", "must not"],
)
@pytest.mark.parametrize("verb", ["prove", "supply", "record"])
@pytest.mark.parametrize("destination", ["the PR body", "a PR comment", "workflow artifacts"])
def test_independent_delivery_prohibition_uses_shared_operation_grammar(
    boundary, negation, verb, destination
):
    assert (
        verifier._required_evidence_channels(
            "The reviewer may supply evidence in the PR body"
            + boundary
            + f"the senior maintainer {negation} {verb} evidence in {destination}"
        )
        == set()
    )


@pytest.mark.parametrize(
    "negative_destination", ["the PR body", "a PR comment", "workflow artifacts"]
)
@pytest.mark.parametrize(
    "positive_destination,channel",
    [("the PR body", "body"), ("a PR comment", "comments"), ("workflow artifacts", "artifacts")],
)
def test_prohibition_does_not_erase_independent_mandatory_delivery(
    negative_destination, positive_destination, channel
):
    assert verifier._required_evidence_channels(
        f"The reviewer does not prove evidence in {negative_destination}"
        + f" and the maintainer must record evidence in {positive_destination}"
    ) == {channel}


@pytest.mark.parametrize("actor", ["reviewer", "assigned reviewer", "senior reviewer", "CI runner"])
def test_supply_clause_subject_preserves_delivery(actor):
    assert verifier._required_evidence_channels(
        f"The {actor} supplies evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize("boundary", [" and ", " while ", "; ", ". ", "! ", "? "])
@pytest.mark.parametrize("negation", ["doesn't", "doesn’t", "does not", "never", "no longer"])
@pytest.mark.parametrize("verb", ["supply", "prove", "record"])
@pytest.mark.parametrize(
    "negative_destination", ["the PR body", "a PR comment", "workflow artifacts"]
)
@pytest.mark.parametrize(
    "positive_destination,channel",
    [("the PR body", "body"), ("a PR comment", "comments"), ("workflow artifacts", "artifacts")],
)
@pytest.mark.parametrize("positive_first", [True, False])
def test_prohibition_polarity_is_clause_order_and_alias_symmetric(
    boundary, negation, verb, negative_destination, positive_destination, channel, positive_first
):
    """Negated aliases cannot invent a channel beside an independent obligation."""
    positive = f"The reviewer must record evidence in {positive_destination}"
    negative = f"the senior maintainer {negation} {verb} evidence in {negative_destination}"
    criterion = positive + boundary + negative if positive_first else negative + boundary + positive
    assert verifier._required_evidence_channels(criterion) == {channel}


@pytest.mark.parametrize("verb", ["proves", "records", "supplies"])
@pytest.mark.parametrize("negation", ["never", "no longer"])
@pytest.mark.parametrize("destination", ["the PR body", "a PR comment", "workflow artifacts"])
def test_bare_finite_negative_delivery_has_no_channel(verb, negation, destination):
    """Finite negative predicates do not require evidence delivery."""
    assert (
        verifier._required_evidence_channels(
            f"The reviewer {negation} {verb} evidence in {destination}"
        )
        == set()
    )


@pytest.mark.parametrize("verb", ["prove", "record", "supply"])
@pytest.mark.parametrize(
    "first_destination,first_channel",
    [("the PR body", "body"), ("a PR comment", "comments"), ("workflow artifacts", "artifacts")],
)
@pytest.mark.parametrize(
    "second_destination,second_channel",
    [("the PR body", "body"), ("a PR comment", "comments"), ("workflow artifacts", "artifacts")],
)
def test_contrastive_not_only_preserves_both_delivery_channels(
    verb, first_destination, first_channel, second_destination, second_channel
):
    """Not-only contrast is additive, not a delivery prohibition."""
    assert verifier._required_evidence_channels(
        f"The reviewer must not only {verb} evidence in {first_destination}"
        + f" but also record evidence in {second_destination}"
    ) == {first_channel, second_channel}


@pytest.mark.parametrize(
    "negative_auxiliary",
    ["does not need to", "doesn't need to", "never has to", "no longer needs to"],
)
@pytest.mark.parametrize("destination", ["the PR body", "a PR comment", "workflow artifacts"])
def test_negative_embedded_mandatory_auxiliary_is_not_required(negative_auxiliary, destination):
    """Embedded need-to/has-to cannot override its negative governor."""
    assert (
        verifier._required_evidence_channels(
            f"Command output {negative_auxiliary} be in {destination}"
        )
        == set()
    )


@pytest.mark.parametrize("participle", ["recorded", "proved", "supplied"])
@pytest.mark.parametrize(
    "first_destination,first_channel",
    [("the PR body", "body"), ("a PR comment", "comments"), ("workflow artifacts", "artifacts")],
)
@pytest.mark.parametrize(
    "second_destination,second_channel",
    [("the PR body", "body"), ("a PR comment", "comments"), ("workflow artifacts", "artifacts")],
)
def test_passive_not_only_preserves_complete_destination_set(
    participle, first_destination, first_channel, second_destination, second_channel
):
    """Additive obligations share the passive aspect grammar."""
    assert verifier._required_evidence_channels(
        f"Evidence must not only be {participle} in {first_destination}"
        + f" but also be recorded in {second_destination}"
    ) == {first_channel, second_channel}


@pytest.mark.parametrize(
    "negative_auxiliary", ["does not need to", "never has to", "no longer needs to"]
)
@pytest.mark.parametrize("participle", ["recorded", "proved", "supplied"])
@pytest.mark.parametrize(
    "negative_destination", ["the PR body", "a PR comment", "workflow artifacts"]
)
@pytest.mark.parametrize(
    "positive_destination,channel",
    [("the PR body", "body"), ("a PR comment", "comments"), ("workflow artifacts", "artifacts")],
)
@pytest.mark.parametrize("positive_first", [True, False])
def test_negative_embedded_governor_preserves_independent_passive_delivery(
    negative_auxiliary,
    participle,
    negative_destination,
    positive_destination,
    channel,
    positive_first,
):
    """Passive prohibitions cannot add a channel or erase a separate obligation."""
    negative = f"Command output {negative_auxiliary} be {participle} in {negative_destination}"
    positive = f"The reviewer must record evidence in {positive_destination}"
    assert verifier._required_evidence_channels(negative) == set()
    criterion = positive + "; " + negative if positive_first else negative + "; " + positive
    assert verifier._required_evidence_channels(criterion) == {channel}


@pytest.mark.parametrize("governor", ["may", "should", "must not", "shall never"])
@pytest.mark.parametrize("first_destination", ["the PR body", "a PR comment", "workflow artifacts"])
@pytest.mark.parametrize(
    "second_destination", ["the PR body", "a PR comment", "workflow artifacts"]
)
def test_elided_passive_inherits_optional_or_negative_governor(
    governor, first_destination, second_destination
):
    """Object inheritance cannot turn an optional or prohibited delivery positive."""
    assert (
        verifier._required_evidence_channels(
            f"Evidence {governor} be recorded in {first_destination}"
            + f" and also be recorded in {second_destination}"
        )
        == set()
    )


@pytest.mark.parametrize("prefix", ["", "- ", "- [ ] ", "* [x] ", "1. "])
def test_supply_imperative_list_marker_preserves_delivery(prefix):
    """List formatting does not turn an imperative delivery into a noun."""
    assert verifier._required_evidence_channels(prefix + "Supply evidence in a PR comment") == {
        "comments"
    }


@pytest.mark.parametrize("auxiliary", ["do", "does", "did"])
@pytest.mark.parametrize("role", ["reviewer", "maintainer"])
@pytest.mark.parametrize("modal", ["may", "can", "could", "would", "should"])
@pytest.mark.parametrize("governor", ["must", "shall", "needs to", "will"])
@pytest.mark.parametrize("operation", ["put", "place", "write"])
@pytest.mark.parametrize(
    "destinations", list(permutations(["the PR body", "a PR comment", "workflow artifacts"], 2))
)
def test_optional_review_predicate_cannot_suppress_elided_mandatory_delivery(
    auxiliary, role, modal, governor, operation, destinations
):
    before, after = destinations
    expected = "body" if "body" in after else "comments" if "comment" in after else "artifacts"
    criterion = f"The {role} {modal} {operation} evidence in {before} and {governor} {operation} evidence in {after}"
    assert verifier._required_evidence_channels(criterion) == {expected}
    assert (
        verifier._required_evidence_channels(
            criterion.replace(f"and {governor} ", f"and {governor} not ")
        )
        == set()
    )
    assert verifier._required_evidence_channels(
        criterion.replace(f"{modal} ", f"{modal} not ")
    ) == {expected}
    assert verifier._required_evidence_channels(
        f"The service {auxiliary} put evidence in its database; " + criterion
    ) == {expected}


@pytest.mark.parametrize("auxiliary", ["do", "does", "did"])
@pytest.mark.parametrize("role", ["reviewer", "maintainer"])
@pytest.mark.parametrize(
    "qualifier", ["after checking the", "before reviewing the", "following inspection of the"]
)
@pytest.mark.parametrize(
    "object_name", ["PR", "pull request", "PR body", "PR comments", "workflow artifacts"]
)
@pytest.mark.parametrize("operation", ["placed", "submitted", "delivered"])
@pytest.mark.parametrize(
    "destination,channel",
    [("the PR body", "body"), ("a PR comment", "comments"), ("workflow artifacts", "artifacts")],
)
def test_review_related_actor_aside_preserves_delivery(
    auxiliary, role, qualifier, object_name, operation, destination, channel
):
    criterion = f"The {role}, {qualifier} {object_name}, {operation} evidence in {destination}"
    assert verifier._required_evidence_channels(criterion) == {channel}
    assert (
        verifier._required_evidence_channels(
            f"The service, {qualifier} {object_name}, {auxiliary} put evidence in its database"
        )
        == set()
    )


@pytest.mark.parametrize("auxiliary", ["do", "does", "did"])
@pytest.mark.parametrize("actor", ["service", "API"])
@pytest.mark.parametrize("operation", ["put", "place", "write", "record"])
@pytest.mark.parametrize(
    "destination", ["in its database", "in the audit log", "to the assigned clients"]
)
def test_do_supported_product_storage_preserves_independent_delivery(
    auxiliary, actor, operation, destination
):
    criterion = f"The {actor} {auxiliary} {operation} evidence {destination}"
    assert verifier._required_evidence_channels(criterion) == set()
    assert (
        verifier._required_evidence_channels(criterion.replace(auxiliary, auxiliary + " not"))
        == set()
    )
    for review_destination, channel in [
        ("the PR body", "body"),
        ("a PR comment", "comments"),
        ("workflow artifacts", "artifacts"),
    ]:
        assert verifier._required_evidence_channels(
            criterion + f"; the reviewer must record evidence in {review_destination}"
        ) == {channel}


@pytest.mark.parametrize(
    "subject",
    [
        "The service must record evidence in its database",
        "Evidence must be recorded in its database by the service",
    ],
)
@pytest.mark.parametrize("separator", [", ", ", and ", " and "])
@pytest.mark.parametrize("preposition", ["in ", ""])
@pytest.mark.parametrize(
    "destinations", list(permutations(["the PR body", "a PR comment", "workflow artifacts"], 2))
)
def test_punctuated_shared_product_review_destinations(
    subject, separator, preposition, destinations
):
    criterion = (
        subject
        + separator
        + preposition
        + destinations[0]
        + separator
        + preposition
        + destinations[1]
    )
    channels = {
        "body" if "body" in d else "comments" if "comment" in d else "artifacts"
        for d in destinations
    }
    assert verifier._required_evidence_channels(criterion) == channels
    assert verifier._required_evidence_channels(criterion.replace("must ", "must not ")) == set()


@pytest.mark.parametrize("role", ["reviewer", "maintainer"])
@pytest.mark.parametrize(
    "qualifier", ["after validating the", "before checking the", "following inspection of the"]
)
@pytest.mark.parametrize(
    "evidence", ["output", "evidence", "artifacts", "transcript", "command output"]
)
@pytest.mark.parametrize("operation", ["placed", "submitted", "delivered"])
@pytest.mark.parametrize(
    "destination,channel",
    [("the PR body", "body"), ("a PR comment", "comments"), ("workflow artifacts", "artifacts")],
)
def test_evidence_related_actor_aside_retains_outer_delivery(
    role, qualifier, evidence, operation, destination, channel
):
    aside = f"{qualifier} {evidence}"
    assert verifier._required_evidence_channels(
        f"The {role}, {aside}, {operation} evidence in {destination}"
    ) == {channel}
    assert (
        verifier._required_evidence_channels(
            f"The service, {aside}, {operation} evidence in its database"
        )
        == set()
    )


@pytest.mark.parametrize("role", ["reviewer", "maintainer", "author", "operator"])
@pytest.mark.parametrize(
    "parenthetical",
    [
        "however",
        "for example",
        "after checking CI",
        "in addition",
        "in particular",
        "at this point",
        "as noted above",
        "after initial validation",
    ],
)
@pytest.mark.parametrize("operation", ["placed", "submitted", "delivered", "wrote"])
def test_parenthetical_actor_preserves_active_past_delivery(role, parenthetical, operation):
    assert verifier._required_evidence_channels(
        f"The {role}, {parenthetical}, {operation} evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize("apostrophe", ["'", "’"])
@pytest.mark.parametrize("actor", ["API", "service"])
def test_parenthetical_product_storage_and_quoted_contractions(actor, apostrophe):
    assert (
        verifier._required_evidence_channels(
            f"The {actor}, however, placed transcripts in its database"
        )
        == set()
    )
    quote_open, quote_close = ("'", "'") if apostrophe == "'" else ("‘", "’")
    assert verifier._required_evidence_channels(
        f"The parser must recognize {quote_open}The reviewer won{apostrophe}t place evidence in the PR body{quote_close}; include evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize(
    "inner",
    [
        "the maintainer recorded evidence in the PR body",
        "evidence was recorded in the PR body",
        "record evidence in the PR body",
        "the maintainer must record evidence in the PR body",
    ],
)
def test_parenthetical_does_not_erase_actual_delivery_predicates(inner):
    assert "body" in verifier._required_evidence_channels(
        f"The reviewer, {inner}, placed evidence in a PR comment"
    )


def test_parenthetical_normalization_preserves_independent_obligations_and_gates():
    assert verifier._required_evidence_channels(
        "Do not merge, without evidence in the PR body, until the reviewer placed evidence in a PR comment"
    ) == {"body", "comments"}
    assert "body" in verifier._required_evidence_channels(
        "The reviewer, the maintainer must place evidence in the PR body, placed evidence in a PR comment"
    )
    assert verifier._required_evidence_channels(
        'The parser must recognize "The reviewer, in addition, placed evidence in the PR body"; the maintainer must place evidence in a PR comment'
    ) == {"comments"}


@pytest.mark.parametrize(
    "quote_open,quote_close", [('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"), ("`", "`")]
)
@pytest.mark.parametrize(
    "destination,channel",
    [("the PR body", "body"), ("a PR comment", "comments"), ("workflow artifacts", "artifacts")],
)
def test_quoted_later_storage_member_preserves_following_reviewer(
    quote_open, quote_close, destination, channel
):
    criterion = (
        "The API must record evidence in its database and record transcripts in its audit log; "
        f"the parser must recognize {quote_open}and record evidence in the PR body{quote_close}; "
        f"the reviewer must record evidence in {destination}"
    )
    assert verifier._required_evidence_channels(criterion) == {channel}


@pytest.mark.parametrize("apostrophe", ["'", "’"])
@pytest.mark.parametrize("operation", ["put", "place", "write", "paste"])
@pytest.mark.parametrize(
    "destination,channel",
    [("a PR comment", "comments"), ("workflow artifacts", "artifacts"), ("the PR body", "body")],
)
def test_multiple_contractions_do_not_form_a_quoted_literal(
    apostrophe, operation, destination, channel
):
    criterion = (
        f"The service won{apostrophe}t have put evidence in its database; "
        f"the reviewer must {operation} evidence in {destination}; "
        f"the operator couldn{apostrophe}t post artifacts"
    )
    assert verifier._required_evidence_channels(criterion) == {channel}


@pytest.mark.parametrize("modal", ["may", "can", "could", "would", "should", "would not"])
@pytest.mark.parametrize("governor", ["must", "shall", "needs to", "will"])
@pytest.mark.parametrize(
    "destination,channel",
    [("the PR body", "body"), ("a PR comment", "comments"), ("workflow artifacts", "artifacts")],
)
def test_direct_storage_governor_reset_retains_mandatory_delivery(
    modal, governor, destination, channel
):
    criterion = f"The service {modal} record evidence in its database and {governor} record evidence in {destination}"
    assert verifier._required_evidence_channels(criterion) == {channel}
    assert (
        verifier._required_evidence_channels(
            criterion.replace(f"and {governor} record", f"and {governor} not record")
        )
        == set()
    )


@pytest.mark.parametrize("actor", ["service", "API"])
@pytest.mark.parametrize(
    "storage", ["in its database", "in the audit log", "to the assigned clients"]
)
@pytest.mark.parametrize(
    "aspect,negative",
    [
        ("must be", "must not be"),
        ("has been", "has not been"),
        ("will be", "will not be"),
        ("was", "was not"),
        ("is", "is not"),
        ("has already been", "has not already been"),
        ("will have been", "will not have been"),
    ],
)
@pytest.mark.parametrize("operation", ["put", "placed", "recorded", "written"])
@pytest.mark.parametrize("preposition", ["in ", ""])
@pytest.mark.parametrize(
    "destination,channel",
    [("the PR body", "body"), ("a PR comment", "comments"), ("workflow artifacts", "artifacts")],
)
def test_passive_product_storage_shared_review_destination(
    actor, storage, aspect, negative, operation, preposition, destination, channel
):
    criterion = (
        f"Evidence {aspect} {operation} {storage} by the {actor} and {preposition}{destination}"
    )
    assert verifier._required_evidence_channels(criterion) == {channel}
    assert verifier._required_evidence_channels(criterion.replace(aspect, negative)) == set()


@pytest.mark.parametrize("role", ["reviewer", "maintainer", "operator"])
@pytest.mark.parametrize(
    "adverbs",
    [
        "already",
        "now",
        "also",
        "still",
        "successfully",
        "already successfully",
        "also now successfully",
    ],
)
@pytest.mark.parametrize("operation", ["placed", "submitted", "delivered"])
@pytest.mark.parametrize(
    "destination,channel",
    [("the PR body", "body"), ("a PR comment", "comments"), ("workflow artifacts", "artifacts")],
)
def test_active_past_delivery_subject_adverbs(role, adverbs, operation, destination, channel):
    assert verifier._required_evidence_channels(
        f"The {role} {adverbs} {operation} evidence in {destination}"
    ) == {channel}
    assert (
        verifier._required_evidence_channels(
            f"The service {adverbs} {operation} evidence in its database"
        )
        == set()
    )


@pytest.mark.parametrize(
    "modal",
    [
        "could",
        "couldn't",
        "couldn’t",
        "wouldn't",
        "wouldn’t",
        "shouldn't",
        "shouldn’t",
        "may",
        "can",
        "should",
    ],
)
@pytest.mark.parametrize("operation", ["put", "place", "write", "record"])
@pytest.mark.parametrize(
    "destination,channel",
    [("a PR comment", "comments"), ("workflow artifacts", "artifacts"), ("the PR body", "body")],
)
def test_optional_modal_aliases_preserve_channels_and_contractions(
    modal, operation, destination, channel
):
    criterion = f"The reviewer {modal} {operation} evidence in {destination}"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + f"; the maintainer must record evidence in {destination}"
    ) == {channel}


@pytest.mark.parametrize("actor", ["API", "service"])
@pytest.mark.parametrize("operation", ["place", "write", "record"])
@pytest.mark.parametrize("conjunction", ["and", "or"])
def test_coordinated_product_storage_keeps_actor_and_delivery_scope(actor, operation, conjunction):
    criterion = f"The {actor} must record evidence in its database {conjunction} {operation} transcripts in its audit log"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(criterion.replace("must ", "must not ")) == set()
    for destination, channel in [
        ("a PR comment", "comments"),
        ("workflow artifacts", "artifacts"),
        ("the PR body", "body"),
    ]:
        assert verifier._required_evidence_channels(
            criterion + f"; the reviewer must record evidence in {destination}"
        ) == {channel}
        assert verifier._required_evidence_channels(
            criterion + f" and record evidence in {destination}"
        ) == {channel}


@pytest.mark.parametrize(
    "governor,operation,gating",
    [
        ("must", "record", True),
        ("must not", "record", False),
        ("has", "recorded", True),
        ("has not", "recorded", False),
        ("will have", "recorded", True),
        ("may", "record", False),
    ],
)
@pytest.mark.parametrize("conjunction", ["and", "or"])
@pytest.mark.parametrize(
    "destination,channel",
    [("a PR comment", "comments"), ("workflow artifacts", "artifacts"), ("the PR body", "body")],
)
@pytest.mark.parametrize(
    "continuation", ["internal", "inherited", "independent", "shared", "reset"]
)
def test_storage_coordination_governor_and_boundary_matrix(
    governor, operation, gating, conjunction, destination, channel, continuation
):
    chain = (
        f"The service {governor} {operation} evidence in its database "
        f"{conjunction} {operation} transcripts in its audit log"
    )
    expected = set()
    if continuation == "internal":
        chain += f" and {operation} command output in its storage"
    elif continuation == "inherited":
        chain += f" and {operation} evidence in {destination}"
        expected = {channel} if gating else set()
    elif continuation == "independent":
        chain += f" and the assigned reviewer must record evidence in {destination}"
        expected = {channel}
    elif continuation == "shared":
        chain += f" and in {destination}"
        expected = {channel} if gating else set()
    else:
        chain += f" and must record evidence in {destination}"
        expected = {channel}
    assert verifier._required_evidence_channels(chain) == expected


@pytest.mark.parametrize("preposition", ["in ", ""])
@pytest.mark.parametrize("polarity", ["", "not "])
def test_storage_coordination_shared_body_destination(polarity, preposition):
    chain = (
        f"The API must {polarity}record evidence in its database and record "
        f"transcripts in its audit log and {preposition}the PR body"
    )
    assert verifier._required_evidence_channels(chain) == (set() if polarity else {"body"})


def test_storage_coordination_parser_literal_and_unsupported_suffix():
    literal = "The API must record evidence in its database and record transcripts in its audit log"
    assert verifier._required_evidence_channels(
        f'The parser must recognize "{literal}"; the reviewer must record evidence in a PR comment'
    ) == {"comments"}
    assert verifier._required_evidence_channels(
        literal + "; an independent reviewer must include evidence in the PR body"
    ) == {"body"}


@pytest.mark.parametrize(
    "predicate", ["isn't", "isn’t", "aren't", "aren’t", "wasn't", "wasn’t", "weren't", "weren’t"]
)
@pytest.mark.parametrize("adverb", ["", "already ", "previously ", "still "])
@pytest.mark.parametrize("destination", ["in the database", "to clients"])
def test_contracted_finite_passive_put_preserves_negation(predicate, adverb, destination):
    criterion = f"Evidence {predicate} {adverb}put {destination} by the service"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; include evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize(
    "predicate",
    [
        "is not",
        "are not",
        "was not",
        "were not",
        "will not be",
        "must not be",
        "is never",
        "was no longer",
    ],
)
@pytest.mark.parametrize("operation", ["putting", "placing", "writing", "pasting", "recording"])
@pytest.mark.parametrize("destination", ["a PR comment", "workflow artifacts", "the PR body"])
def test_negated_progressive_delivery_has_no_channel(predicate, operation, destination):
    criterion = f"The reviewer {predicate} {operation} evidence in {destination}"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; include evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize(
    "predicate",
    [
        "is",
        "are",
        "was",
        "were",
        "is being",
        "was being",
        "is already",
        "was previously",
        "is not",
        "was never",
        "is no longer",
    ],
)
@pytest.mark.parametrize("operation", ["put", "placed", "written", "pasted", "recorded"])
@pytest.mark.parametrize("destination", ["in the database", "to clients"])
def test_finite_passive_product_storage_has_no_channel(predicate, operation, destination):
    criterion = f"Evidence {predicate} {operation} {destination} by the service"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; include evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize("operation", ["record", "put", "place"])
@pytest.mark.parametrize("preposition", ["in ", ""])
@pytest.mark.parametrize(
    "destination,channel",
    [("a PR comment", "comments"), ("workflow artifacts", "artifacts"), ("the PR body", "body")],
)
def test_product_storage_shared_review_destination(operation, preposition, destination, channel):
    criterion = (
        f"The service must {operation} evidence in its database and {preposition}{destination}"
    )
    assert verifier._required_evidence_channels(criterion) == {channel}
    assert verifier._required_evidence_channels(criterion.replace("must ", "must not ")) == set()
    assert verifier._required_evidence_channels(
        criterion + "; the maintainer must include evidence in a PR comment"
    ) == {channel, "comments"}


@pytest.mark.parametrize("operation", ["put", "placed", "written", "pasted"])
@pytest.mark.parametrize("predicate", ["must be", "has been", "must have been"])
@pytest.mark.parametrize("destination", ["in the database", "to clients"])
def test_passive_product_aliases_share_bound_destination(operation, predicate, destination):
    criterion = f"Validation evidence {predicate} {operation} {destination} by the service"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; include evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize("modal", ["may", "can", "could", "should"])
@pytest.mark.parametrize("operation", ["put", "place", "write", "paste"])
@pytest.mark.parametrize("destination", ["a PR comment", "workflow artifacts", "the PR body"])
def test_negated_optional_modal_alias_is_not_required(modal, operation, destination):
    criterion = f"The reviewer {modal} not {operation} evidence in {destination}"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; the maintainer must record evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize(
    "predicate",
    ["must be recorded", "must have been recorded", "has been recorded", "is being recorded"],
)
@pytest.mark.parametrize("destination", ["the database", "the audit log"])
def test_passive_product_storage_preserves_independent_delivery(predicate, destination):
    criterion = f"Validation evidence {predicate} in {destination} by the service"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; the reviewer must record evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize(
    "criterion",
    [
        "The service has written command output to clients",
        "The service must have written command output to clients",
        "The service is writing command output to clients",
        "Validation evidence must be written to clients by the service",
        "Validation evidence has been written to clients by the service",
        "Validation evidence must have been written to clients by the service",
    ],
)
def test_product_recipient_aspects_preserve_independent_delivery(criterion):
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; the reviewer must record evidence in workflow artifacts"
    ) == {"artifacts"}


@pytest.mark.parametrize(
    "predicate", ["must record", "has recorded", "is recording", "must have recorded"]
)
@pytest.mark.parametrize(
    "destination,channel",
    [("a PR comment", "comments"), ("workflow artifacts", "artifacts"), ("the PR body", "body")],
)
def test_optional_case_object_is_not_optional_delivery(predicate, destination, channel):
    assert verifier._required_evidence_channels(
        f"The service must record transcripts in its database; the reviewer {predicate} optional-case test transcript in {destination}"
    ) == {channel}


@pytest.mark.parametrize(
    "auxiliary",
    [
        "has not",
        "have never",
        "had not",
        "has not already",
        "hasn't",
        "hadn’t",
        "will not have",
        "won’t have",
    ],
)
@pytest.mark.parametrize("verb", ["put", "placed", "pasted", "written", "recorded"])
@pytest.mark.parametrize("destination", ["a PR comment", "the PR body", "a workflow artifact"])
def test_perfect_negated_aliases_preserve_independent_delivery(auxiliary, verb, destination):
    criterion = f"The reviewer {auxiliary} {verb} validation evidence in {destination}"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; the maintainer must record evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize(
    "auxiliary", ["has not yet", "hasn't yet", "had not yet", "won’t yet have"]
)
@pytest.mark.parametrize("verb", ["put", "placed", "recorded"])
def test_yet_perfect_negation_preserves_independent_delivery(auxiliary, verb):
    criterion = f"The reviewer {auxiliary} {verb} validation evidence in a PR comment"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(criterion + "; record evidence in the PR body") == {
        "body"
    }


@pytest.mark.parametrize(
    "noun",
    [
        "validation evidence",
        "exact-head regression command output",
        "independently collected artifacts",
        "optional-case test transcript",
    ],
)
@pytest.mark.parametrize("verb", ["put", "placed", "recorded"])
def test_qualified_product_storage_preserves_independent_delivery(noun, verb):
    criterion = f"The service {verb} {noun} in its audit log"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; record evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize("auxiliary", ["must", "shall", "needs to", "will"])
@pytest.mark.parametrize("aspect", ["put", "be putting", "have put", "have been placing"])
@pytest.mark.parametrize("noun", ["validation evidence", "regression command output"])
@pytest.mark.parametrize("destination", ["database", "audit log"])
def test_modal_product_storage_aspects_preserve_independent_delivery(
    auxiliary, aspect, noun, destination
):
    criterion = f"The service {auxiliary} {aspect} {noun} in its {destination}"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; record evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize("boundary", [".", "!", "?"])
def test_sentence_product_clause_preserves_active_past_delivery(boundary):
    assert verifier._required_evidence_channels(
        f"The API must include command output{boundary} The reviewer placed evidence in a PR comment."
    ) == {"comments"}


@pytest.mark.parametrize(
    "auxiliary",
    [
        "will not have",
        "will never have",
        "will no longer have",
        "will also have",
        "will not already have",
    ],
)
@pytest.mark.parametrize("verb", ["placed", "put"])
def test_future_perfect_product_storage_modifier_positions(auxiliary, verb):
    criterion = f"The application {auxiliary} {verb} transcripts in its database"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; record evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize(
    "auxiliary", ["won't have", "won’t have", "won't already have", "won’t also have"]
)
@pytest.mark.parametrize("verb", ["placed", "put"])
def test_contracted_future_perfect_storage_preserves_independent_delivery(auxiliary, verb):
    criterion = f"The application {auxiliary} {verb} transcripts in its database"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; record evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize("boundary", ["but", "while", "because", "whereas", "although"])
def test_compound_product_clause_preserves_active_past_placed(boundary):
    criterion = f"The API must include command output, {boundary} the reviewer placed evidence in a PR comment"
    assert verifier._required_evidence_channels(criterion) == {"comments"}


@pytest.mark.parametrize("auxiliary", ["has", "had", "will have"])
@pytest.mark.parametrize("verb", ["placed", "put"])
def test_perfect_product_storage_is_not_evidence(auxiliary, verb):
    criterion = f"The application {auxiliary} {verb} transcripts in its database"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; record evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize("actor", ["assigned reviewer", "author", "maintainer", "API"])
@pytest.mark.parametrize("marker", ["- [ ]", "+ [X]", "1. [ ]"])
def test_active_past_placed_delivery_is_not_a_participial_modifier(actor, marker):
    assert verifier._required_evidence_channels(
        f"{marker} The {actor} placed validation evidence in a PR comment"
    ) == {"comments"}
    assert (
        verifier._required_evidence_channels("The application placed transcripts in its database")
        == set()
    )
    assert verifier._required_evidence_channels(
        "Record placed validation evidence in the PR body"
    ) == {"body"}


@pytest.mark.parametrize("verb", ["put", "place"])
@pytest.mark.parametrize(
    "destination,channel", [("a PR comment", "comments"), ("the PR body", "body")]
)
def test_put_place_share_review_delivery_boundaries(verb, destination, channel):
    criterion = f"The author must {verb} command output in {destination}"
    assert verifier._required_evidence_channels(criterion) == {channel}
    assert verifier._required_evidence_channels(
        f"{verb.title()} the command output in {destination}"
    ) == {channel}
    assert (
        verifier._required_evidence_channels(
            f"The author must not {verb} command output in {destination}"
        )
        == set()
    )
    assert (
        verifier._required_evidence_channels(f"The API must {verb} command output in its database")
        == set()
    )


@pytest.mark.parametrize("verb", ["include", "contain", "have"])
@pytest.mark.parametrize("actor", ["API", "application", "service"])
def test_product_response_vocabulary_preserves_independent_review_delivery(verb, actor):
    criterion = f"The {actor} must {verb} command output"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; record evidence in a PR comment"
    ) == {"comments"}
    assert verifier._required_evidence_channels(
        f"The reviewer must {verb} command output in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize("verb", ["paste", "write"])
@pytest.mark.parametrize(
    "destination,channel", [("a PR comment", "comments"), ("the PR body", "body")]
)
def test_pasted_and_written_review_delivery(verb, destination, channel):
    criterion = f"The reviewer must {verb} command output into {destination}"
    assert verifier._required_evidence_channels(criterion) == {channel}
    assert (
        verifier._required_evidence_channels(
            f"The reviewer must not {verb} command output into {destination}"
        )
        == set()
    )
    assert verifier._required_evidence_channels(
        criterion + "; the service must provide command output to clients"
    ) == {channel}


@pytest.mark.parametrize("modifier", ["supporting", "supporting execution", "validation"])
def test_modified_product_evidence_link_field(modifier):
    criterion = f"The API response must include links to {modifier} evidence"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; paste command output into a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize("noun", ["Evidence", "Before/after evidence", "Command output"])
@pytest.mark.parametrize("requirement", ["required", "needed", "mandatory"])
def test_preposed_body_destination_consumes_complete_predicate(noun, requirement):
    criterion = f"{noun} in the PR body is {requirement}"
    assert verifier._required_evidence_channels(criterion) == {"body"}
    assert (
        verifier._required_evidence_channels(f"{noun} in the PR body is not {requirement}") == set()
    )
    assert verifier._required_evidence_channels(
        criterion + "; write command output into a PR comment"
    ) == {"body", "comments"}


@pytest.mark.parametrize("actor", ["service", "application", "API", "endpoint"])
def test_product_provides_output_without_erasing_review_delivery(actor):
    criterion = f"The {actor} must provide command output to clients"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; write command output into a PR comment"
    ) == {"comments"}
    assert verifier._required_evidence_channels(
        "The reviewer must provide command output to a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize(
    "verb,canonical",
    [
        ("paste", "record"),
        ("pastes", "records"),
        ("pasted", "recorded"),
        ("pasting", "recording"),
        ("write", "record"),
        ("writes", "records"),
        ("written", "recorded"),
        ("writing", "recording"),
        ("wrote", "recorded"),
    ],
)
def test_delivery_lexical_aliases_share_existing_grammar(verb, canonical):
    for sentence in [
        "The reviewer must {verb} evidence in a PR comment",
        "Evidence must not be {verb} in a PR comment; record evidence in the PR body",
        "The application must {verb} transcripts in its database",
    ]:
        assert verifier._required_evidence_channels(sentence.format(verb=verb)) == (
            verifier._required_evidence_channels(sentence.format(verb=canonical))
        )


@pytest.mark.parametrize("participle", ["pasted", "written"])
def test_passive_delivery_alias_preserves_negation(participle):
    assert verifier._required_evidence_channels(
        f"Evidence must be {participle} in a PR comment"
    ) == {"comments"}
    assert verifier._required_evidence_channels(
        f"Evidence must not be {participle} in a PR comment; record evidence in the PR body"
    ) == {"body"}


@pytest.mark.parametrize("status", ["not optional", "never optional", "no longer optional"])
@pytest.mark.parametrize(
    "criterion", ["Evidence in the PR body is {status}", "The PR body is {status}"]
)
def test_negated_optionality_is_mandatory_body_delivery(status, criterion):
    assert verifier._required_evidence_channels(criterion.format(status=status)) == {"body"}


@pytest.mark.parametrize("operation", ["write", "record", "paste"])
@pytest.mark.parametrize("destination", ["clients", "users", "consumers"])
def test_canonical_record_output_to_product_recipients(operation, destination):
    criterion = f"The service must {operation} command output to {destination}"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; write command output in a PR comment"
    ) == {"comments"}
    assert verifier._required_evidence_channels(
        "The service must write command output in the PR body"
    ) == {"body"}


@pytest.mark.parametrize("name", ["write", "paste"])
@pytest.mark.parametrize("quote", ["", "`", '"'])
def test_delivery_aliases_do_not_rewrite_command_names(name, quote):
    criterion = f"The {quote}{name}{quote} command must output evidence"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; paste command output in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize("name", ["write evidence", "paste evidence"])
@pytest.mark.parametrize("quotes", [("`", "`"), ('"', '"'), ("'", "'"), ("“", "”")])
def test_alias_normalization_preserves_quoted_multitoken_names(name, quotes):
    criterion = f"The {quotes[0]}{name}{quotes[1]} command must output evidence"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; paste command output in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize("name", ["write to disk", "paste into form", "write to the PR"])
@pytest.mark.parametrize("quote", ["", "`", '"'])
def test_alias_normalization_preserves_qualified_command_names(name, quote):
    criterion = f"The {quote}{name}{quote} command must output evidence"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; paste command output in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize("operation", ["provide", "write", "return", "display", "emit", "render"])
@pytest.mark.parametrize(
    "destination,channel",
    [("workflow artifacts", "artifacts"), ("the PR", "overall"), ("the PR body", "body")],
)
def test_product_recipient_preserves_coordinated_review_delivery(operation, destination, channel):
    criterion = f"The service must {operation} command output to clients and in {destination}"
    assert verifier._required_evidence_channels(criterion) == {channel}
    assert verifier._required_evidence_channels(
        criterion + "; paste command output in a PR comment"
    ) == {channel, "comments"}
    assert (
        verifier._required_evidence_channels(
            f"The service must {operation} command output to clients; must not attach it in {destination}"
        )
        == set()
    )


@pytest.mark.parametrize("operation", ["provide", "return", "display", "emit", "render", "expose"])
def test_product_shortcut_preserves_workflow_artifact_delivery(operation):
    criterion = f"The service must {operation} command output in workflow artifacts"
    assert verifier._required_evidence_channels(criterion) == {"artifacts"}


@pytest.mark.parametrize(
    "criterion,expected",
    [
        (
            "The service must provide command output to clients and in the PR body, a PR comment and workflow artifacts",
            {"body", "comments", "artifacts"},
        ),
        ("The UI must render command output to clients and in the PR body editor", set()),
        (
            "The UI must render command output to clients and in the PR body editor and workflow artifacts",
            {"artifacts"},
        ),
        (
            "The service must not provide command output to clients and in the PR body, a PR comment and workflow artifacts",
            set(),
        ),
    ],
)
def test_shared_destination_lists_preserve_review_and_editor_channels(criterion, expected):
    assert verifier._required_evidence_channels(criterion) == expected
    assert verifier._required_evidence_channels(
        criterion + "; record evidence in a PR comment"
    ) == expected | {"comments"}


@pytest.mark.parametrize("artifact_source", ["CI", "GitHub Actions"])
def test_recognized_artifact_destinations_share_body_channel_classification(artifact_source):
    criterion = f"The service must provide command output to clients and in the PR body and {artifact_source} artifacts"
    assert verifier._required_evidence_channels(criterion) == {"body", "artifacts"}
    assert (
        verifier._required_evidence_channels(criterion.replace("must provide", "must not provide"))
        == set()
    )


@pytest.mark.parametrize("modifier", ["written", "pasted"])
@pytest.mark.parametrize("operation", ["displays", "shows", "renders"])
def test_participial_alias_modifier_is_not_a_second_delivery(operation, modifier):
    criterion = f"- [ ] The UI {operation} {modifier} evidence to users"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; record evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize("recipient", ["clients", "its users", "the consumers"])
@pytest.mark.parametrize(
    "destination,channel",
    [("a PR comment", "comments"), ("workflow artifacts", "artifacts"), ("the PR body", "body")],
)
def test_product_recipient_shared_destination_is_not_split(recipient, destination, channel):
    criterion = f"The service must provide command output to {recipient} and {destination}"
    assert verifier._required_evidence_channels(criterion) == {channel}


@pytest.mark.parametrize(
    "auxiliary", ["has to", "have to", "is required to", "is expected to", "is obliged to"]
)
@pytest.mark.parametrize("operation", ["returned", "displayed", "provided"])
def test_shared_auxiliary_reaches_passive_review_requirement_gate(auxiliary, operation):
    criterion = f"Command output {auxiliary} be {operation} in a PR comment by the service"
    assert verifier._required_evidence_channels(criterion) == {"comments"}
    negative = f"Command output does not have to be {operation} in a PR comment by the service"
    assert verifier._required_evidence_channels(negative) == set()
    assert verifier._required_evidence_channels(negative + "; record evidence in the PR body") == {
        "body"
    }


@pytest.mark.parametrize("product", ["service", "API", "application", "endpoint"])
@pytest.mark.parametrize("verb", ["provided", "returned", "displayed"])
def test_reverse_product_output_retains_explicit_comment_delivery(product, verb):
    """An explicit review destination takes precedence over a product actor."""
    criterion = f"Command output must be {verb} in a PR comment by the {product}"
    assert verifier._required_evidence_channels(criterion) == {"comments"}


@pytest.mark.parametrize("actor", ["service", "API", "API response"])
@pytest.mark.parametrize(
    "object_,channel", [("artifacts", "artifacts"), ("command output", "overall")]
)
def test_product_provide_cannot_erase_explicit_pr_delivery(actor, object_, channel):
    criterion = f"The {actor} must provide {object_} in the PR"
    assert verifier._required_evidence_channels(criterion) == {channel}


@pytest.mark.parametrize(
    "criterion",
    [
        "Evidence is not written in a PR comment",
        "Evidence is not being pasted in a PR comment",
        "Never write evidence in a PR comment",
        "Never paste evidence in a PR comment",
    ],
)
def test_record_aliases_preserve_non_modal_prohibitions(criterion):
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(criterion + "; record evidence in the PR body") == {
        "body"
    }


@pytest.mark.parametrize("participle", ["written", "pasted", "recorded"])
@pytest.mark.parametrize("recipient", ["clients", "users", "consumers"])
def test_reverse_record_output_binds_its_own_recipient(participle, recipient):
    criterion = f"Command output is {participle} to {recipient} by the service"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(criterion + "; write evidence in a PR comment") == {
        "comments"
    }


@pytest.mark.parametrize(
    "criterion,channel",
    [
        ("The reviewer must paste command output into a PR comment", "comments"),
        ("Evidence in the PR body is required", "body"),
        ("Evidence in the PR body is not optional", "body"),
        ("Command output must be provided in a PR comment by the service", "comments"),
        ("The API response must include links to supporting evidence", None),
        ("The service must provide command output to clients", None),
        ("The service must write command output to clients", None),
        ("The service must provide artifacts in the PR", "artifacts"),
        ("The service must provide command output in the PR", "overall"),
        ("Evidence is not written in a PR comment", None),
        ("Command output is written to clients by the service", None),
        (
            "The service must provide command output to clients and in workflow artifacts",
            "artifacts",
        ),
        ("The service must provide command output to clients and in the PR", "overall"),
        ("The service must provide command output to clients and in the PR body", "body"),
        ("The service must provide command output to clients and in a PR comment", "comments"),
        ("The write to the PR command must output evidence", None),
    ],
)
@pytest.mark.parametrize("status", ["present", "absent", "unavailable"])
def test_fresh_canary_findings_control_actual_coverage_floor(criterion, channel, status):
    spec = importlib.util.spec_from_file_location(
        "fresh_canary_coverage_fixtures",
        Path(__file__).with_name("test_pr_verifier_prompt_coverage.py"),
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    context, _ = fixture._context(1, 1000, 1000)
    context = context.replace(fixture.ACCEPTANCE_SENTINEL, criterion).replace(
        "## PR Diff Summary",
        f"## Acceptance evidence\n\n- Overall retrieval status: **{status if channel == 'overall' else 'absent'}**\n"
        f"- PR body: **{status if channel == 'body' else 'absent'}**\n"
        f"- PR comments: **{status if channel == 'comments' else 'absent'}**\n"
        f"- Referenced workflow artifacts: **{status if channel == 'artifacts' else 'absent'}**\n\n## PR Diff Summary",
    )
    result = verifier._apply_coverage_floor(
        verifier.EvaluationResult(verdict="PASS", used_llm=True),
        verifier.prompt_coverage(context, None),
    )
    assert result.verdict == ("CONCERNS" if channel and status != "present" else "PASS")


@pytest.mark.parametrize("prefix", ["", "- [ ] "])
@pytest.mark.parametrize(
    "status,expected", [("present", "PASS"), ("absent", "CONCERNS"), ("unavailable", "CONCERNS")]
)
def test_generated_docs_drift_body_requirement_controls_floor(prefix, status, expected):
    finding = fix_agent.Finding(
        source="semantic-scan",
        kind="semantic",
        doc_path="README.md",
        target="old claim",
        detail="stale",
        authoritative_source="scripts/example.py",
    )
    criterion = fix_agent.semantic_verification_requirements([finding])[0]
    assert "record the before/after evidence in the pull request body" in criterion
    assert verifier._required_evidence_channels(prefix + criterion) == {"body"}
    spec = importlib.util.spec_from_file_location(
        "producer_coverage_fixtures",
        Path(__file__).with_name("test_pr_verifier_prompt_coverage.py"),
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    context, _ = fixture._context(1, 1000, 1000)
    context = context.replace(fixture.ACCEPTANCE_SENTINEL, prefix + criterion).replace(
        "## PR Diff Summary",
        f"## Acceptance evidence\n\n- Overall retrieval status: **absent**\n- PR body: **{status}**\n- PR comments: **absent**\n- Referenced workflow artifacts: **absent**\n\n## PR Diff Summary",
    )
    result = verifier._apply_coverage_floor(
        verifier.EvaluationResult(verdict="PASS", used_llm=True),
        verifier.prompt_coverage(context, None),
    )
    assert result.verdict == expected


@pytest.mark.parametrize("modal", ["must", "shall", "needs to"])
def test_existential_comment_requirement(modal):
    channels = verifier._required_evidence_channels(
        f"- [ ] There {modal} be a PR comment with command output"
    )
    assert channels == {"comments"}


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


@pytest.mark.parametrize("operation", ["return", "display", "emit", "render", "expose"])
def test_product_delivery_operations_share_the_body_channel(operation):
    criterion = f"The service must {operation} evidence in the PR body"
    assert verifier._required_evidence_channels(criterion) == {"body"}
    assert (
        verifier._required_evidence_channels(
            f"The service must not {operation} evidence in the PR body"
        )
        == set()
    )
    assert verifier._required_evidence_channels(
        criterion + "; record command output in a PR comment"
    ) == {"body", "comments"}


@pytest.mark.parametrize("determiner", ["the", "its", "our", "all the", "all its"])
@pytest.mark.parametrize("recipient", ["clients", "users", "consumers"])
def test_forward_and_reverse_record_share_determined_recipients(determiner, recipient):
    for criterion in [
        f"The service must write command output to {determiner} {recipient}",
        f"Command output is written to {determiner} {recipient} by the service",
    ]:
        assert verifier._required_evidence_channels(criterion) == set()
        assert verifier._required_evidence_channels(
            criterion + "; record command output in a PR comment"
        ) == {"comments"}


@pytest.mark.parametrize(
    "auxiliary",
    [
        "needs to",
        "need to",
        "has to",
        "have to",
        "is required to",
        "is expected to",
        "is supposed to",
        "is obliged to",
        "is mandated to",
    ],
)
@pytest.mark.parametrize(
    "destination,channel", [("the PR", "overall"), ("a PR comment", "comments")]
)
def test_reverse_review_delivery_shares_mandatory_auxiliaries(auxiliary, destination, channel):
    criterion = f"Command output {auxiliary} be provided in {destination} by the service"
    assert verifier._required_evidence_channels(criterion) == {channel}


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


@pytest.mark.parametrize("wrapper", ["Here is the result:\n{}", "```json\n{}\n```"])
def test_failed_repair_does_not_render_wrapped_stale_pass(monkeypatch, wrapper):
    raw = wrapper.format('{"verdict": "PASS", "summary": "Unvalidated result"}')
    monkeypatch.setattr(
        verifier, "_build_verifier_repair_callback", lambda _client: lambda *_args: None
    )
    result = verifier._parse_llm_response(raw, "test-provider", client=object())
    assert result.verdict == "CONCERNS"
    assert result.error
    text = verifier._evaluation_output_text(result)
    assert text.startswith("Verdict: CONCERNS")
    assert '"verdict": "PASS"' not in text


@pytest.mark.parametrize("wrapper", ["Explanation:\n{}", "```json\n{}\n```"])
def test_wrapped_nonpass_detail_is_preserved(wrapper):
    raw = wrapper.format('{"verdict": "CONCERNS", "detail": "Missing exact-head witness"}')
    result = verifier.EvaluationResult(verdict="CONCERNS", raw_content=raw)
    assert "Missing exact-head witness" in verifier._evaluation_output_text(result)


@pytest.mark.parametrize(
    "raw",
    [
        'Schema example: {"verdict":"PASS"}. Missing exact-head witness; repair failed.',
        '{"verdict":"CONCERNS","example":{"verdict":"PASS"},"detail":"Missing exact-head witness"}',
    ],
)
def test_incidental_pass_object_does_not_erase_actionable_diagnostics(raw):
    result = verifier.EvaluationResult(verdict="CONCERNS", raw_content=raw)
    text = verifier._evaluation_output_text(result)
    assert "Missing exact-head witness" in text
    assert '"verdict":"PASS"' not in text


@pytest.mark.parametrize(
    "criterion",
    [
        "The PR body must not include evidence",
        "The pull request body shall not include evidence",
        "Evidence must not be included in the PR body",
        "The PR body is not required",
        "The PR body does not need to include evidence",
        "The PR body is not required to include evidence",
        "The PR body must never include evidence",
        "Evidence must never be included in the PR body",
        "Evidence shall never be included in the PR body",
        "There must not be evidence in the PR body",
        "Evidence must not be shown in the PR body",
        "Evidence must not be added in the PR body",
    ],
)
def test_negated_body_delivery_does_not_require_evidence(criterion):
    assert verifier._required_evidence_channels("- [ ] " + criterion) == set()
    channels = verifier._required_evidence_channels(
        "- [ ] " + criterion + "; include evidence in a PR comment"
    )
    assert channels == {"comments"}


@pytest.mark.parametrize(
    "criterion",
    [
        "Evidence is required in the PR body",
        "There must be evidence in the PR body",
    ],
)
def test_equivalent_body_obligations_keep_destination_specific_floor(criterion):
    channels = verifier._required_evidence_channels("- [ ] " + criterion)
    assert channels == {"body"}
    mixed = verifier._required_evidence_channels(
        "- [ ] " + criterion + "; the reviewer must post a PR comment with command output"
    )
    assert mixed == {"comments", "body"}
    assert verifier._required_evidence_is_missing(
        "- Overall retrieval status: **present**\n- PR body: **absent**\n"
        "- PR comments: **present**\n- Referenced workflow artifacts: **present**",
        mixed,
    )


@pytest.mark.parametrize("actor", ["UI", "application", "service"])
@pytest.mark.parametrize("operation", ["should show", "must include"])
def test_body_editor_product_output_is_not_a_reviewer_deliverable(actor, operation):
    criterion = f"The {actor} {operation} evidence in the pull request body editor"
    assert verifier._required_evidence_channels("- [ ] " + criterion) == set()
    channels = verifier._required_evidence_channels(
        "- [ ] " + criterion + "; include evidence in the PR body"
    )
    assert channels == {"body"}
    human = verifier._required_evidence_channels(
        "- [ ] The reviewer of the UI must show evidence in the PR body"
    )
    assert human == {"body"}


BODY_CLAUSE_CASES = []
for modal in ("must", "shall"):
    for polarity in ("", "not ", "never "):
        expected = {"body"} if not polarity else set()
        for aspect in ("be", "have been", "have been being"):
            BODY_CLAUSE_CASES.append(
                (f"Evidence {modal} {polarity}{aspect} included in the PR body", expected)
            )
        for operation in ("include", "contain", "show"):
            BODY_CLAUSE_CASES.append(
                (f"The PR body {modal} {polarity}{operation} evidence", expected)
            )
for modal in ("must", "shall", "needs to"):
    for polarity in ("", "not ", "never "):
        BODY_CLAUSE_CASES.append(
            (
                f"There {modal} {polarity}be evidence in the PR body",
                {"body"} if not polarity else set(),
            )
        )
for actor in ("UI", "application", "service"):
    for operation in ("include", "show", "store"):
        for modal in ("must", "should"):
            BODY_CLAUSE_CASES.append(
                (f"The {actor} {modal} {operation} evidence in the pull request body editor", set())
            )
BODY_CLAUSE_CASES.extend(
    [
        ("The PR body must contain no before/after evidence", set()),
        ("There must be no before/after evidence in the PR body", set()),
        ("Record no before/after evidence in the pull request body", set()),
        ("The PR body must not exclude the before/after evidence", {"body"}),
        ("Evidence must be included in a PR comment and in the PR body", {"body", "comments"}),
        ("Evidence must be included in the PR body and in a PR comment", {"body", "comments"}),
        ("The PR body must exclude evidence", set()),
        ("The PR body must omit evidence", set()),
        ("The PR body must remove evidence", set()),
        ("The PR body must not exclude evidence", {"body"}),
        ("The UI allows users to show evidence in the pull request body editor", set()),
        ("The UI enables users to show evidence in the pull request body editor", set()),
        ("The UI supports users to show evidence in the pull request body editor", set()),
        ("The PR body must contain no evidence", set()),
        ("The PR body must include no evidence", set()),
        ("No evidence must be included in the PR body", set()),
        (
            "The UI must include evidence in both workflow artifacts and the PR body editor",
            {"artifacts"},
        ),
        ("The UI must include evidence in both a PR comment and the PR body editor", {"comments"}),
        ("The UI must contain evidence in the PR body editor", set()),
        ("Include evidence in both the PR body and a PR comment", {"body", "comments"}),
        ("Evidence must be included in the PR body with optional artifacts", {"body"}),
        ("The reviewer of the UI must include evidence in the PR body", {"body"}),
        ("The UI must include evidence in the PR body", {"body"}),
        ("The engineer must include evidence in the PR body", {"body"}),
        ("Do not merge without evidence in the PR body", {"body"}),
        (
            "The UI must show evidence in the pull request body editor that the reviewer must include in the PR body",
            {"body"},
        ),
    ]
)
for destinations in permutations(("the PR body", "a PR comment", "a workflow artifact")):
    for separator in (" and ", ", "):
        BODY_CLAUSE_CASES.append(
            (
                "Evidence must be included in " + separator.join(destinations),
                {"body", "comments", "artifacts"},
            )
        )
    BODY_CLAUSE_CASES.append(
        (
            "Evidence must be included in " + " and in ".join(destinations),
            {"body", "comments", "artifacts"},
        )
    )


@pytest.mark.parametrize(
    "criterion",
    [
        "The PR body must include a summary",
        "The parser must recognize headings in the PR body",
        "The PR body must be formatted as Markdown",
    ],
)
def test_ordinary_body_behavior_is_not_an_evidence_delivery(criterion):
    assert verifier._required_evidence_channels("- [ ] " + criterion) == set()
    assert verifier._required_evidence_channels(
        "- [ ] " + criterion + "; include evidence in the PR body"
    ) == {"body"}


@pytest.mark.parametrize("criterion,expected", BODY_CLAUSE_CASES)
@pytest.mark.parametrize("prefix", ["- ", "- [ ] "])
@pytest.mark.parametrize("comment_position", ["none", "before", "after", "and"])
def test_body_clause_matrix_preserves_independent_destinations(
    criterion, expected, prefix, comment_position
):
    comment = "the reviewer must post a PR comment with command output"
    if comment_position == "before":
        criterion = comment + "; " + criterion
    elif comment_position == "after":
        criterion += "; " + comment
    elif comment_position == "and":
        criterion += " and " + comment
    expected = expected | ({"comments"} if comment_position != "none" else set())
    actual = verifier._required_evidence_channels(prefix + criterion)
    assert actual == expected


@pytest.mark.parametrize("criterion,expected", BODY_CLAUSE_CASES)
@pytest.mark.parametrize("status", ["present", "absent", "unavailable"])
@pytest.mark.parametrize("channel", ["body", "comments", "artifacts"])
def test_body_clause_matrix_controls_real_coverage_floor(criterion, expected, status, channel):
    spec = importlib.util.spec_from_file_location(
        "clause_coverage_fixtures", Path(__file__).with_name("test_pr_verifier_prompt_coverage.py")
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    context, _ = fixture._context(1, 1000, 1000)
    context = context.replace(fixture.ACCEPTANCE_SENTINEL, criterion)
    statuses = {
        name: status if name == channel else "present" for name in ("body", "comments", "artifacts")
    }
    context = context.replace(
        "## PR Diff Summary",
        "## Acceptance evidence\n\n- Overall retrieval status: **present**\n"
        f"- PR body: **{statuses['body']}**\n- PR comments: **{statuses['comments']}**\n"
        f"- Referenced workflow artifacts: **{statuses['artifacts']}**\n\n## PR Diff Summary",
    )
    coverage = verifier.prompt_coverage(context, None)
    result = verifier._apply_coverage_floor(
        verifier.EvaluationResult(verdict="PASS", used_llm=True), coverage
    )
    assert result.verdict == ("CONCERNS" if channel in expected and status != "present" else "PASS")


@pytest.mark.parametrize("predicate", ["must describe the change", "should describe the change"])
def test_product_recipient_does_not_absorb_independent_review_predicate(predicate):
    criterion = f"The service must provide command output to clients, and the PR body {predicate}"
    assert verifier._required_evidence_channels("- [ ] " + criterion) == set()
    assert verifier._required_evidence_channels(
        "- [ ] " + criterion + "; include evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize("operation", ["presents", "sends", "delivers"])
@pytest.mark.parametrize("modifier", ["written", "pasted"])
def test_product_participial_modifiers_do_not_depend_on_governing_verb_allowlist(
    operation, modifier
):
    criterion = f"The UI {operation} {modifier} evidence to users"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; include evidence in a PR comment"
    ) == {"comments"}


@pytest.mark.parametrize("artifact_source", ["workflow", "CI", "GitHub Actions"])
def test_named_review_artifact_delivery_object_is_preserved(artifact_source):
    criterion = f"The service must provide {artifact_source} artifacts"
    assert verifier._required_evidence_channels(criterion) == {"artifacts"}
    assert (
        verifier._required_evidence_channels(
            "The service must not provide " + artifact_source + " artifacts"
        )
        == set()
    )


@pytest.mark.parametrize("operation", ["return", "display", "emit", "render", "expose"])
def test_shared_response_operations_retain_explicit_comment_delivery(operation):
    assert verifier._required_evidence_channels(
        f"The reviewer must {operation} evidence in a PR comment"
    ) == {"comments"}
    assert (
        verifier._required_evidence_channels(
            f"The reviewer must not {operation} evidence in a PR comment"
        )
        == set()
    )


@pytest.mark.parametrize("auxiliary", ["must", "shall", "has to"])
def test_modal_negated_body_optionality_remains_mandatory(auxiliary):
    assert verifier._required_evidence_channels(
        f"Evidence in the PR body {auxiliary} not be optional"
    ) == {"body"}


@pytest.mark.parametrize("modifier", ["required", "generated", "audit", "release"])
def test_positive_modified_artifact_delivery_survives_product_shortcut(modifier):
    criterion = f"The service must provide {modifier} evidence in workflow artifacts"
    assert verifier._required_evidence_channels(criterion) == {"artifacts"}
    assert (
        verifier._required_evidence_channels(
            "The service must not provide " + modifier + " evidence in workflow artifacts"
        )
        == set()
    )


@pytest.mark.parametrize(
    "passive",
    [
        "has not been written",
        "had never been pasted",
        "can not be written",
        "has not been freshly written",
        "had never been previously pasted",
        "can not be manually written",
    ],
)
def test_perfect_and_modal_passive_aliases_preserve_prohibition(passive):
    criterion = f"Evidence {passive} in a PR comment"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; include evidence in the PR body"
    ) == {"body"}


@pytest.mark.parametrize("negation", ["never", "no longer"])
@pytest.mark.parametrize("operation", ["return", "display", "emit", "render", "expose"])
def test_negated_obligations_preserve_response_operation_polarity(negation, operation):
    criterion = f"The reviewer is {negation} required to {operation} evidence in a PR comment"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; include evidence in the PR body"
    ) == {"body"}


@pytest.mark.parametrize("operation", ["write", "paste"])
@pytest.mark.parametrize(
    "destination", ["outside a PR comment", "in the issue rather than a PR comment"]
)
def test_excluded_comment_destination_retains_generic_evidence_not_comment(operation, destination):
    criterion = f"The reviewer must {operation} evidence {destination}"
    assert verifier._required_evidence_channels(criterion) == {"overall"}
    assert verifier._required_evidence_channels(
        criterion + "; include evidence in a PR comment"
    ) == {"overall", "comments"}


@pytest.mark.parametrize(
    "destination,channel",
    [("workflow artifacts", "artifacts"), ("a PR comment", "comments"), ("the PR body", "body")],
)
def test_coordinated_evidence_object_inherits_governing_delivery(destination, channel):
    assert verifier._required_evidence_channels(
        f"The service must provide command output to clients and evidence in {destination}"
    ) == {channel}
    assert (
        verifier._required_evidence_channels(
            f"The service must not provide command output to clients and evidence in {destination}"
        )
        == set()
    )


@pytest.mark.parametrize("participle", ["written", "pasted"])
def test_alias_and_shared_destination_grammar_preserve_both_prefix(participle):
    assert verifier._required_evidence_channels(
        f"Evidence must be {participle} in both the PR body and a PR comment"
    ) == {"body", "comments"}
    assert (
        verifier._required_evidence_channels(
            f"Evidence must not be {participle} in both the PR body and a PR comment"
        )
        == set()
    )


@pytest.mark.parametrize("modal", ["may", "can", "should"])
@pytest.mark.parametrize("operation", ["write", "paste"])
@pytest.mark.parametrize("destination", ["a PR comment", "workflow artifacts", "the PR body"])
def test_optional_delivery_modal_does_not_become_a_mandatory_alias(modal, operation, destination):
    criterion = f"The reviewer {modal} {operation} evidence in {destination}"
    assert verifier._required_evidence_channels(criterion) == set()
    assert verifier._required_evidence_channels(
        criterion + "; include evidence in a PR comment"
    ) == {"comments"}
