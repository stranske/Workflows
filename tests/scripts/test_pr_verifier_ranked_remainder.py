"""Behavior selected from the verified #4481 final-head Gate missing-line log."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from scripts.langchain import pr_verifier as verifier

from tests.scripts.test_pr_verifier_file_chunks import Client, patch


@pytest.mark.parametrize(
    ("repaired", "expected"),
    [
        pytest.param(None, None, id="no-repair"),
        pytest.param([{"type": "thinking", "thinking": "metadata"}], None, id="metadata-only"),
        pytest.param([{"type": "text", "text": "   "}], None, id="blank-text"),
        pytest.param(
            [
                {"type": "thinking", "thinking": "private metadata"},
                {"type": "text", "text": '{"verdict":'},
                {"type": "text", "text": '"PASS"}'},
            ],
            '{"verdict":"PASS"}',
            id="text-blocks",
        ),
    ],
)
def test_schema_repair_returns_only_usable_response_text(monkeypatch, repaired, expected) -> None:
    client = object()
    repair = Mock(return_value=repaired)
    factory = Mock(return_value=repair)
    cap = Mock(return_value="bounded raw response")
    monkeypatch.setattr(verifier, "build_repair_callback", factory)
    monkeypatch.setattr(verifier, "_cap_prompt_text", cap)

    callback = verifier._build_verifier_repair_callback(client)
    result = callback("schema", "validation errors", "raw response")

    assert result == expected
    assert factory.call_count == 1
    wrapped = factory.call_args.args[0]
    assert isinstance(wrapped, verifier._CapacityCheckedRepairClient)
    assert wrapped.client is client
    cap.assert_called_once_with("raw response", verifier.EVAL_SCHEMA_REPAIR_BUDGET_TOKENS)
    repair.assert_called_once_with("schema", "validation errors", "bounded raw response")


@pytest.fixture
def chunk_review(monkeypatch):
    monkeypatch.delenv("VERIFIER_SEMANTIC_MODE", raising=False)
    monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE", raising=False)
    monkeypatch.setenv("VERIFIER_DIFF_BUDGET_TOKENS", "16000")
    return patch("first.py", 40000) + patch("second.py", 40000)


@pytest.mark.parametrize("finding", ["PASS", "CONCERNS", "FAIL"])
def test_failed_synthesis_keeps_review_credit_and_local_findings(
    monkeypatch, chunk_review, finding
) -> None:
    client = Client([finding, "PASS"])
    invoke = verifier._invoke_llm

    def fail_synthesis(client, prompt, *, operation, **kwargs):
        if operation == "evaluate_pr_chunk_synthesis":
            raise RuntimeError("synthesis provider unavailable")
        return invoke(client, prompt, operation=operation, **kwargs)

    monkeypatch.setattr(verifier, "_invoke_llm", fail_synthesis)
    result = verifier._evaluate_chunked(
        client, "Review all requirements.", chunk_review, "openai", "m"
    )

    assert result is not None
    assert result.verdict == ("UNVERIFIABLE_INPUT" if finding == "PASS" else finding)
    assert result.error == "synthesis provider unavailable"
    assert "Cross-file acceptance reconciliation unavailable" in result.summary
    assert result.concerns == (["Real code defect"] if finding != "PASS" else [])
    assert result.files_not_reviewed == []
    assert result.input_coverage["files_complete"] == 2
    assert result.used_llm is True
    assert len(client.prompts) == 2
    assert result.resolved_chunk_concerns == []


@pytest.mark.parametrize("required_evidence_absent", [False, True])
def test_chunk_coverage_rejection_prevents_calls_and_review_credit(
    monkeypatch, chunk_review, required_evidence_absent
) -> None:
    client = Client()
    coverage = verifier.prompt_coverage

    def reject_local_context(context, diff, *, evaluate_minimum=True):
        measured = coverage(context, diff, evaluate_minimum=evaluate_minimum)
        return replace(
            measured,
            reasons=("Assigned review evidence is unavailable.",),
            required_evidence_absent=required_evidence_absent,
        )

    monkeypatch.setattr(verifier, "prompt_coverage", reject_local_context)
    result = verifier._evaluate_chunked(
        client, "Review all requirements.", chunk_review, "openai", "m"
    )

    assert result is not None
    assert result.verdict == ("CONCERNS" if required_evidence_absent else "UNVERIFIABLE_INPUT")
    assert result.files_not_reviewed == ["first.py", "second.py"]
    assert result.input_coverage["files_complete"] == 0
    assert result.input_coverage["sufficient"] is False
    assert result.used_llm is False
    assert client.prompts == []
    assert len(result.chunk_reviews) == 2
    for review in result.chunk_reviews:
        assert review["prompt_coverage"]["reasons"] == ["Assigned review evidence is unavailable."]
        assert "prompt_sha256" not in review
        assert "provider_result" not in review


def test_oversized_unparseable_diff_withholds_unknown_file_review(chunk_review) -> None:
    client = Client()
    # A large diff capture without Git file headers cannot establish which
    # complete files a provider would be reviewing.
    result = verifier._evaluate_chunked(
        client, "Review all requirements.", "x" * 80000, "openai", "m"
    )

    assert result is not None
    assert result.verdict == "UNVERIFIABLE_INPUT"
    assert result.files_not_reviewed == ["(unknown changed files)"]
    assert "Changed-file inventory is unavailable" in result.summary
    assert result.provider_used == "openai" and result.model == "m"
    assert result.used_llm is False
    assert client.prompts == []


def test_oversized_file_request_cap_preserves_unreviewed_tail(monkeypatch, chunk_review) -> None:
    monkeypatch.setattr(verifier, "MAX_REVIEW_CHUNKS", 1)
    client = Client()
    first, second = patch("first.py", 70000), patch("second.py", 70000)

    result = verifier._evaluate_chunked(
        client, "Review all requirements.", first + second, "openai", "m"
    )

    assert result is not None
    assert result.verdict == "UNVERIFIABLE_INPUT"
    assert result.files_not_reviewed == ["second.py"]
    assert result.input_coverage["files_total"] == 2
    assert result.input_coverage["files_complete"] == 1
    assert result.input_coverage["chunks"] == 1
    assert result.input_coverage["sufficient"] is False
    assert result.used_llm is True
    assert len(client.prompts) == 1
    assert first.strip() in client.prompts[0]
    assert second.strip() not in client.prompts[0]
    assert result.chunk_reviews[0]["assigned_files"] == ["first.py"]


def test_comparison_chunks_use_comparison_operation_and_reconcile(
    monkeypatch, chunk_review
) -> None:
    client = Client()
    invoke = Mock(wraps=verifier._invoke_llm)
    monkeypatch.setattr(verifier, "_invoke_llm", invoke)

    result = verifier._evaluate_chunked(
        client, "Review all requirements.", chunk_review, "openai", "m", evaluate_minimum=False
    )

    assert result is not None
    assert result.verdict == "PASS"
    assert result.files_not_reviewed == []
    assert result.input_coverage["files_complete"] == 2
    assert result.used_llm is True
    assert [call.kwargs["operation"] for call in invoke.call_args_list] == [
        "evaluate_pr_compare_chunk",
        "evaluate_pr_compare_chunk",
        "evaluate_pr_chunk_synthesis",
    ]
    assert [call.kwargs.get("diff") for call in invoke.call_args_list] == [
        patch("first.py", 40000),
        patch("second.py", 40000),
        None,
    ]
    assert len(client.prompts) == 3


def test_response_fallback_propagates_second_string_conversion_memory_error() -> None:
    class ExhaustedOnRetry:
        def __init__(self):
            self.calls = 0

        def __str__(self):
            self.calls += 1
            if self.calls == 1:
                raise ValueError("initial serialization failed")
            raise MemoryError("fallback exhausted memory")

    response = ExhaustedOnRetry()
    with pytest.raises(MemoryError, match="fallback exhausted memory"):
        verifier._coerce_response_content(response)
    assert response.calls == 2


@pytest.fixture
def native_slots(monkeypatch):
    """Fake SDK boundaries while running the real frozen-slot admission logic."""
    monkeypatch.delenv("LANGCHAIN_MODEL", raising=False)
    configured = [
        SimpleNamespace(provider="openai", model="first-model"),
        SimpleNamespace(provider="anthropic", model="second-model"),
    ]
    raw = [object(), object()]
    prepared = [
        SimpleNamespace(root_client=SimpleNamespace(max_retries=0)),
        SimpleNamespace(_client=SimpleNamespace(max_retries=0)),
    ]
    contracts = [
        {"provider": slot.provider, "model": slot.model, "endpoint": f"native-{index}"}
        for index, slot in enumerate(configured)
    ]
    prepare = Mock(side_effect=lambda client: prepared[raw.index(client)])
    contract = Mock(side_effect=lambda client, **kwargs: contracts[prepared.index(client)])
    monkeypatch.setattr(verifier, "_prepare_capacity_client", prepare)
    monkeypatch.setattr(verifier, "_native_capacity_contract", contract)
    # Tuple labels do not attest to the actual SDK contract.
    clients = [(client, "untrusted-label", "untrusted-model") for client in raw]
    return SimpleNamespace(
        configured=configured,
        clients=clients,
        prepared=prepared,
        contracts=contracts,
        prepare=prepare,
        contract=contract,
    )


@pytest.mark.parametrize("field", ["provider", "model"])
def test_semantic_slot_mismatch_rejects_native_contract(native_slots, field) -> None:
    native_slots.contracts[1][field] = "different-native-value"

    with pytest.raises(verifier.InputCapacityError, match="does not match frozen configured slot"):
        verifier._semantic_slots_and_clients(
            native_slots.clients, None, None, native_slots.configured
        )

    assert native_slots.prepare.call_args_list == [call(row[0]) for row in native_slots.clients]
    assert native_slots.contract.call_args_list == [call(item) for item in native_slots.prepared]


@pytest.mark.parametrize("index", [0, 1], ids=["openai", "anthropic"])
@pytest.mark.parametrize("retries", [None, 1], ids=["unattested", "retries-enabled"])
def test_semantic_slots_require_zero_native_sdk_retries(native_slots, index, retries) -> None:
    sdk = (
        native_slots.prepared[index].root_client
        if index == 0
        else native_slots.prepared[index]._client
    )
    if retries is None:
        del sdk.max_retries
    else:
        sdk.max_retries = retries

    with pytest.raises(verifier.InputCapacityError, match="retries must be disabled"):
        verifier._semantic_slots_and_clients(
            native_slots.clients, None, None, native_slots.configured
        )

    assert native_slots.contract.call_count == index + 1


@pytest.mark.parametrize("paired", [False, True], ids=["ordinary", "paired-trial"])
@pytest.mark.parametrize("synthetic", [False, True], ids=["native", "synthetic"])
def test_semantic_slots_preserve_overrides_trial_sdk_checks_and_provenance(
    monkeypatch, native_slots, paired, synthetic
) -> None:
    monkeypatch.setenv("LANGCHAIN_MODEL", "unused-environment-model")
    native_slots.contracts[0]["model"] = "first-override"
    native_slots.contracts[1]["model"] = "second-override"
    if synthetic:
        native_slots.contracts[1]["provenance"] = "synthetic-unit-test-only"
    trial = Mock() if paired else None

    slots, clients, authentic = verifier._semantic_slots_and_clients(
        native_slots.clients,
        "first-override",
        "second-override",
        native_slots.configured,
        trial=trial,
    )

    assert [(slot["slot_id"], slot["provider"], slot["model"]) for slot in slots] == [
        ("slot-1", "openai", "first-override"),
        ("slot-2", "anthropic", "second-override"),
    ]
    assert [slot["transport"] for slot in slots] == ["native-0", "native-1"]
    assert clients["slot-1"] is native_slots.prepared[0]
    assert clients["slot-2"] is native_slots.prepared[1]
    assert authentic is (not synthetic)
    assert native_slots.contract.call_args_list == [
        call(item, **({"trial": trial} if paired else {})) for item in native_slots.prepared
    ]
    if paired:
        assert trial.check_sdk.call_args_list == [
            call(native_slots.prepared[0].root_client),
            call(native_slots.prepared[1]._client),
        ]


@pytest.mark.parametrize("depth", [0, 2])
def test_semantic_package_prompt_retains_bytes_selected_obligations_and_chain_depth(
    monkeypatch, depth
) -> None:
    monkeypatch.setenv("CHAIN_DEPTH", str(depth))
    monkeypatch.setattr(verifier, "_load_prompt", lambda: "Context:\n{context}\nDiff:\n{diff}")
    dependency_text = "# Closed dependency\n\u00e9 = 1\n" + "source bytes\n" * 500
    prepared = {"prompts": {"review-1": {"bytes": dependency_text.encode("utf-8")}}}
    selected = {"id": "criterion-1", "text": "Preserve complete reviewed code."}
    contract = {"clauses": [selected, {"id": "criterion-2", "text": "Unassigned obligation."}]}

    prompt = verifier._semantic_package_prompt(
        prepared, {"id": "review-1", "clause_ids": ["criterion-1"]}, contract
    )

    assert dependency_text in prompt
    assert '"id": "criterion-1"' in prompt
    assert selected["text"] in prompt
    assert "criterion-2" not in prompt and "Unassigned obligation." not in prompt
    assert "Complete changed-code dependencies are included in the reviewed spans above." in prompt
    if depth:
        assert prompt.endswith(verifier.CHAIN_DEPTH_ADDENDUM.format(depth=depth))
    else:
        assert "Follow-up Iteration Context" not in prompt


@pytest.fixture
def diagnostic_review(monkeypatch):
    """Simulate admission boundaries while exercising recovery and response parsing."""
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    monkeypatch.setenv("VERIFIER_PARTITION_RECOVERY", "diagnostic")
    plan = {
        "acceptance_sufficient": False,
        "ranges": [{"capacity": {"request_sha256": "planned-request"}} for _ in range(3)],
        "results": [],
    }
    client = SimpleNamespace(invoke=Mock())
    monkeypatch.setattr(verifier, "_prepare_capacity_client", lambda value: value)
    monkeypatch.setattr(
        verifier, "_plan_diagnostic_partitions", Mock(return_value=(plan, ["a", "b", "c"]))
    )
    preflight = Mock(return_value={"request_sha256": "planned-request", "status": "PASS"})
    monkeypatch.setattr(verifier, "_preflight_input_capacity", preflight)
    overflow = verifier.InputCapacityError(
        "whole request too large", receipt={"status": "overflow"}
    )
    return SimpleNamespace(client=client, plan=plan, preflight=preflight, overflow=overflow)


def test_diagnostic_changed_request_blocks_generation_and_retains_capacity(diagnostic_review):
    review = diagnostic_review
    changed = {"request_sha256": "changed-request", "status": "PASS"}
    review.preflight.return_value = changed

    result = verifier._maybe_recover_partition_diagnostics(
        review.overflow, review.client, "context", None, "openai", "model"
    )

    review.client.invoke.assert_not_called()
    review.preflight.assert_called_once_with(review.client, "a")
    assert result.verdict == "CONCERNS" and result.used_llm is False
    assert result.error == "diagnostic request changed after planning"
    assert result.partition_recovery["status"] == "diagnostic_incomplete"
    assert result.partition_recovery["acceptance_sufficient"] is False
    assert result.partition_recovery["overflow"] == {"status": "overflow"}
    assert result.partition_recovery["results"] == [
        {"range_index": 0, "error": result.error, "capacity": changed}
    ]


def test_diagnostic_sparse_failure_survives_multiple_malformed_responses(diagnostic_review):
    review = diagnostic_review
    # Plain string responses exercise the real response fallback and parser.
    raw = ['{"verdict":"FAIL","concerns":["confirmed defect"]}', "invalid one", "invalid two"]
    review.client.invoke.side_effect = raw

    result = verifier._maybe_recover_partition_diagnostics(
        review.overflow, review.client, "context", None, "openai", "model"
    )

    assert review.client.invoke.call_count == review.preflight.call_count == 3
    assert [call.args[0] for call in review.client.invoke.call_args_list] == ["a", "b", "c"]
    assert result.verdict == "FAIL" and result.used_llm is True
    assert result.raw_content == "\n\n".join(raw)
    assert result.summary == (
        "Cross-range obligations remain unresolved; diagnostic partition review cannot grant PASS."
    )
    parse_error = "Failed to parse JSON response: JSONDecodeError"
    assert result.error == f"{parse_error}; {parse_error}"
    assert result.concerns[1:] == [
        "confirmed defect",
        f"Diagnostic range 1: {parse_error}",
        f"Diagnostic range 2: {parse_error}",
    ]
    assert result.partition_recovery["status"] == "diagnostic_incomplete"
    assert result.partition_recovery["acceptance_sufficient"] is False
    assert [row["raw_content"] for row in result.partition_recovery["results"]] == raw


def test_comparison_trace_links_keep_provider_labels_when_an_earlier_trace_is_absent():
    results = [
        verifier.EvaluationResult(verdict="PASS", provider_used="openai", used_llm=True),
        verifier.EvaluationResult(
            verdict="CONCERNS",
            provider_used="anthropic",
            used_llm=True,
            langsmith_trace_url="https://smith.langchain.com/r/second-trace",
        ),
        verifier.EvaluationResult(
            verdict="FAIL",
            used_llm=True,
            langsmith_trace_url="https://smith.langchain.com/r/third-trace",
        ),
    ]

    report = verifier.format_comparison_report(results)

    assert report.split("### 🔍 LangSmith Traces\n", 1)[1] == (
        "- [anthropic](https://smith.langchain.com/r/second-trace)\n"
        "- [provider-3](https://smith.langchain.com/r/third-trace)\n"
    )


@pytest.fixture
def fitting_evidence():
    return (
        "## Acceptance evidence\n"
        "- Overall retrieval status: **present**\n"
        "- PR body: **present**\n"
        "- PR comments: **present**\n"
        "- Referenced workflow artifacts: **present**\n"
        "### Bounded PR body\nbody proof\n"
    )


@pytest.mark.parametrize("suffix", [" trailing text", " ", "\t"])
def test_evidence_fitting_rejects_malformed_channel_boundaries(fitting_evidence, suffix):
    evidence = fitting_evidence + "### Bounded PR comments" + suffix + "\noptional history"

    assert verifier._fit_required_evidence_prompt(evidence, [{"body"}], 1) is None


@pytest.mark.parametrize("fence", ["```text", "~~~~"])
def test_evidence_fitting_rejects_unterminated_proof_fences(fitting_evidence, fence):
    evidence = fitting_evidence + fence + "\n### Bounded PR comments\nunterminated proof"

    assert verifier._fit_required_evidence_prompt(evidence, [{"body"}], 1) is None


def test_evidence_fitting_keeps_fenced_heading_lookalikes_in_required_proof(fitting_evidence):
    quoted = "```text\n### Bounded PR comments trailing text\nQUOTED_PROOF\n```"
    required = fitting_evidence.replace("\n### Bounded PR body", "\n\n### Bounded PR body") + quoted
    evidence = required + "\n### Bounded PR comments\nOPTIONAL_HISTORY"

    assert verifier._fit_required_evidence_prompt(evidence, [{"body"}], 1) == (
        required,
        ("body",),
        ("comments",),
        len(required),
    )


@pytest.mark.parametrize("status", ["absent", "unavailable", "present-without-section", "overall"])
def test_evidence_fitting_rejects_unusable_channel_alternatives(fitting_evidence, status):
    evidence = fitting_evidence
    if status in {"absent", "unavailable"}:
        evidence += "### Bounded PR comments\nretained comment text"
        evidence = evidence.replace("PR comments: **present**", f"PR comments: **{status}**")
    channels = {"overall"} if status == "overall" else {"comments"}

    assert verifier._fit_required_evidence_prompt(evidence, [channels], 10000) is None


def test_evidence_fitting_requires_a_real_evidence_section(fitting_evidence):
    preamble = fitting_evidence.split("### Bounded PR body", 1)[0]

    # An empty authored duty still needs a real channel before any projection
    # can be certified; status declarations alone are not captured proof.
    assert verifier._fit_required_evidence_prompt(preamble, [set()], 10000) is None


@pytest.mark.parametrize("body_first", [False, True])
def test_evidence_fitting_selects_smallest_complete_alternative_and_keeps_selected_proof(
    fitting_evidence, body_first
):
    preamble, body = fitting_evidence.rstrip().split("\n### Bounded PR body\n")
    body_section = "### Bounded PR body\n" + body * 100
    comments = "### Bounded PR comments\nshort proof"
    selected = "### Selected required artifact proof\nSELECTED_ARTIFACT_PROOF"
    evidence = "\n".join([preamble, body_section, comments, selected])
    options = [{"body"}, {"comments"}] if body_first else [{"comments"}, {"body"}]
    expected = "\n\n".join([preamble, comments, selected])

    assert verifier._fit_required_evidence_prompt(evidence, options, 1) == (
        expected,
        ("comments",),
        ("body",),
        len(expected),
    )


@pytest.mark.parametrize("spare_chars", [0, -1])
def test_evidence_fitting_optional_section_respects_exact_budget(fitting_evidence, spare_chars):
    required = fitting_evidence.rstrip().replace("\n### Bounded PR body", "\n\n### Bounded PR body")
    optional = "### Bounded PR comments\noptional history"
    budget = len(required) + 2 + len(optional) + spare_chars

    rendered, channels, omitted, required_chars = verifier._fit_required_evidence_prompt(
        required + "\n" + optional, [{"body"}], budget
    )

    assert channels == ("body",)
    assert required_chars == len(required)
    assert rendered == (required + "\n\n" + optional if spare_chars == 0 else required)
    assert omitted == (() if spare_chars == 0 else ("comments",))
