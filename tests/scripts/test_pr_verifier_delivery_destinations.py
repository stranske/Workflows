"""Exact canary findings: destination completeness and actionable text output."""

import importlib.util
from pathlib import Path

import pytest
from scripts.langchain import pr_verifier as verifier


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
def test_body_clause_matrix_controls_real_coverage_floor(criterion, expected, status):
    spec = importlib.util.spec_from_file_location(
        "clause_coverage_fixtures", Path(__file__).with_name("test_pr_verifier_prompt_coverage.py")
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    context, _ = fixture._context(1, 1000, 1000)
    context = context.replace(fixture.ACCEPTANCE_SENTINEL, criterion)
    context = context.replace(
        "## PR Diff Summary",
        "## Acceptance evidence\n\n- Overall retrieval status: **present**\n"
        f"- PR body: **{status}**\n- PR comments: **present**\n"
        "- Referenced workflow artifacts: **present**\n\n## PR Diff Summary",
    )
    coverage = verifier.prompt_coverage(context, None)
    result = verifier._apply_coverage_floor(
        verifier.EvaluationResult(verdict="PASS", used_llm=True), coverage
    )
    assert result.verdict == ("CONCERNS" if "body" in expected and status != "present" else "PASS")
