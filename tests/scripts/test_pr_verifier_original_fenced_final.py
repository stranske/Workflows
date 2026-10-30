"""Offline original final-text recovery; no provider, repair, or new judgment."""

import hashlib
import json
from pathlib import Path

import pytest
from scripts.langchain import pr_verifier as verifier

FINAL = Path(__file__).parents[1] / "fixtures/verifier-original-final/opus-canary984-final.txt"
SHA256 = "a80e3b6eb417182a22851c42246d618540f96048fc15d5b62161348690fa0177"


def original_final():
    raw = FINAL.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SHA256
    return raw.decode()


def test_original_opus_final_recovers_offline_with_exact_raw_provenance():
    raw = original_final()
    expected = verifier._parse_semantic_evaluation_payload(raw)
    result = verifier._parse_llm_response(raw, "anthropic", client=None)
    assert result.error is None
    assert result.verdict == expected.verdict == "FAIL"
    assert result.confidence == expected.confidence == 0.85
    assert result.scores == expected.scores
    assert result.scores.model_dump() == {
        "correctness": 4.0,
        "completeness": 2.0,
        "quality": 6.0,
        "testing": 1.0,
        "risks": 9.0,
    }
    assert result.concerns == expected.concerns and len(result.concerns) == 6
    assert result.summary == expected.summary
    assert result.raw_content == raw
    assert hashlib.sha256(result.raw_content.encode()).hexdigest() == SHA256


def test_valid_original_never_constructs_or_invokes_schema_repair(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("A valid original final must not request schema repair")

    monkeypatch.setattr(verifier, "_build_verifier_repair_callback", forbidden)
    result = verifier._parse_llm_response(original_final(), "anthropic", client=object())
    assert result.error is None and result.verdict == "FAIL"


@pytest.mark.parametrize(
    "entries",
    [
        [
            {"criterion": "Correctness", "support": "The lane guard is installed."},
            {"criterion": "Completeness", "support": "The busy-lane path is covered."},
            {"criterion": "Quality", "support": "The lock remains bounded."},
            {"criterion": "Testing", "support": "Focused tests pass."},
            {"criterion": "Risks", "support": "No owner is evicted."},
            {"criterion": "Verdict", "support": "No concerns found."},
        ],
        [
            {"criterion": "Correctness", "support": "The floor is reconciled."},
            {"criterion": "Completeness", "support": "The timeout is bounded."},
            {"criterion": "Quality", "support": "The configuration is local."},
            {"criterion": "Verdict", "support": "Ready for review."},
        ],
    ],
)
def test_typed_summary_entries_canonicalize_to_scalar_without_repair(monkeypatch, entries):
    def forbidden(*args, **kwargs):
        pytest.fail("A typed summary transport must not request schema repair")

    monkeypatch.setattr(verifier, "_build_verifier_repair_callback", forbidden)
    raw = json.dumps({"verdict": "PASS", "summary": entries})
    expected = "\n\n".join(f"{entry['criterion']}: {entry['support']}" for entry in entries)

    payload = verifier._parse_semantic_evaluation_payload(raw)
    result = verifier._parse_llm_response(raw, "openai", client=object())

    assert payload.summary == expected
    assert result.error is None
    assert result.summary == expected
    assert result.raw_content == raw
    assert "- Summary: " + expected in verifier._format_followup_issue_body(
        result, pr_number=1, pr_url=None, run_url=None
    )


@pytest.mark.parametrize(
    "summary",
    [
        [],
        [{"criterion": "Only one field"}],
        [{"criterion": "Criterion", "support": "Support", "extra": "untrusted"}],
        [{"criterion": 1, "support": "Support"}],
        [{"criterion": "Criterion", "support": 1}],
        [{"criterion": "", "support": "Support"}],
        [{"criterion": "Criterion", "support": ""}],
    ],
)
def test_invalid_summary_entry_transport_remains_refused(summary):
    raw = json.dumps({"verdict": "PASS", "summary": summary})
    with pytest.raises((ValueError, TypeError)):
        verifier._parse_semantic_evaluation_payload(raw)
    result = verifier._parse_llm_response(raw, "openai", client=None)
    assert result.error is not None
    assert result.verdict == "CONCERNS"
    assert result.summary is None
    assert result.raw_content == raw


@pytest.mark.parametrize(
    "payload",
    [
        {
            "verdict": "NOT_A_VERDICT",
            "summary": [{"criterion": "Criterion", "support": "Support"}],
        },
        {
            "verdict": "PASS",
            "summary": [{"criterion": "Criterion", "support": "Support"}],
            "untrusted_authority": "accept",
        },
        {
            "verdict": "PASS",
            "summary": [{"criterion": "Criterion", "support": "Support"}],
            "concerns": [1],
        },
    ],
)
def test_typed_summary_transport_cannot_bypass_semantic_validation(payload):
    raw = json.dumps(payload)
    with pytest.raises((ValueError, TypeError)):
        verifier._parse_semantic_evaluation_payload(raw)
    result = verifier._parse_llm_response(raw, "openai", client=None)
    assert result.error is not None
    assert result.verdict == "CONCERNS"
    assert result.raw_content == raw


@pytest.mark.parametrize(
    "raw",
    [
        '```json\n{"verdict":"FAIL"}\n{"verdict":"PASS"}\n```',
        'Here is the result:\n```json\n{"verdict":"FAIL"}\n```',
        '```json\n{"verdict":"FAIL"}',
        '````json\n{"verdict":"FAIL"}\n```',
        '```json\n{"verdict":"INVALID"}\n```',
        '```json\n{"verdict":"FAIL","confidence":2}\n```',
        '```json\n{"verdict":"FAIL","verdict":"PASS"}\n```',
        '```json\n{"verdict":"FAIL","extra_field":true}\n```',
    ],
)
def test_invalid_transport_or_schema_remains_refused_without_repair(raw):
    result = verifier._parse_llm_response(raw, "anthropic", client=None)
    assert result.error is not None and result.scores is None
    assert result.raw_content == raw


def test_verifier_rejects_bare_unknown_data_without_legacy_fallback():
    raw = json.dumps({"verdict": "FAIL", "legacy_extra": "not authority"})
    result = verifier._parse_llm_response(raw, "anthropic", client=None)
    assert result.error is not None and result.scores is None
    assert result.raw_content == raw


@pytest.mark.parametrize("mutation", ["duplicate", "unknown_extra"])
def test_complete_original_fence_rejects_duplicate_or_unknown_extra_data(mutation):
    raw = original_final()
    if mutation == "duplicate":
        raw = raw.replace('"verdict": "FAIL"', '"verdict": "PASS", "verdict": "FAIL"', 1)
    else:
        raw = raw.replace("{", '{"untrusted_authority": "accept",', 1)
    assert raw != original_final()
    with pytest.raises(ValueError):
        verifier._parse_semantic_evaluation_payload(raw)
    result = verifier._parse_llm_response(raw, "anthropic", client=None)
    assert result.error is not None and result.scores is None
    assert result.raw_content == raw


@pytest.mark.parametrize("fenced", [False, True])
@pytest.mark.parametrize("mutation", ["duplicate", "unknown_extra", "bad_schema"])
def test_all_final_text_uses_strict_parser_without_repair(monkeypatch, fenced, mutation):
    def forbidden(*args, **kwargs):
        pytest.fail("No default provider repair is permitted for a final answer")

    monkeypatch.setattr(verifier, "_build_verifier_repair_callback", forbidden)
    raw = original_final()
    if mutation == "duplicate":
        raw = raw.replace('"verdict": "FAIL"', '"verdict": "PASS", "verdict": "FAIL"', 1)
    elif mutation == "unknown_extra":
        raw = raw.replace("{", '{"untrusted_authority": "accept",', 1)
    else:
        raw = raw.replace('"verdict": "FAIL"', '"verdict": "INVALID"', 1)
    if not fenced:
        raw = raw.removeprefix("```json\n").removesuffix("\n```")
    result = verifier._parse_llm_response(raw, "anthropic", client=object())
    assert result.error and result.scores is None and result.raw_content == raw
