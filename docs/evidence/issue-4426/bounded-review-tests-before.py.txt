"""Behavior selected from the verified #4481 final-head Gate missing-line log."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import Mock

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
