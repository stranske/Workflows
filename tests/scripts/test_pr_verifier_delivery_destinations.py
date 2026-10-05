"""Exact canary findings: destination completeness and actionable text output."""

import importlib.util
from itertools import permutations
from pathlib import Path

import pytest
from scripts import docs_drift_fix_agent as fix_agent
from scripts.langchain import pr_verifier as verifier


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
