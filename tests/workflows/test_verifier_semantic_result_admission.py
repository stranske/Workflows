"""Real semantic producer/matrix, inert native boundary; never call a provider."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.langchain import pr_verifier
from tools import llm_registry, verifier_semantic_rules
from tools import verifier_corpus_evidence as admission

from tests.workflows.test_verifier_expanded_comparison import run_workflow


@pytest.fixture
def semantic_payload(tmp_path, monkeypatch, request):
    fixture = Path(__file__).parents[1] / "fixtures/verifier_semantic_packages"
    capture = json.loads((fixture / "capture.json").read_text())
    monkeypatch.setattr(verifier_semantic_rules, "RULES_PATH", fixture / "rules.json")
    monkeypatch.setattr(pr_verifier, "_semantic_capture", lambda *_: capture)
    monkeypatch.setenv("VERIFIER_SEMANTIC_MODE", "1")
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    key = tmp_path / "fixture-auth-key"
    key.write_bytes(b"a" * 32)
    monkeypatch.setenv("VERIFIER_SEMANTIC_KEY_PATH", str(key))
    configured = llm_registry.resolve_slots()[:2]
    slots = [
        {
            "slot_id": f"slot-{i+1}",
            "provider": slot.provider,
            "model": slot.model,
            "transport": "native",
            "config_sha256": str(i + 1) * 64,
        }
        for i, slot in enumerate(configured)
    ]
    calls = []
    selected = getattr(request, "param", "PASS")
    single_package = selected == "single_package"
    verdict = "PASS" if single_package else selected
    if single_package:
        monkeypatch.setattr(pr_verifier, "prepare_reviewed_execution", lambda *_: None)

    class InertClient:
        def __init__(self, slot):
            self.slot = slot

        def invoke(self, prompt):
            calls.append((self.slot, hashlib.sha256(prompt.encode()).hexdigest()))
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "verdict": verdict,
                        "concerns": [] if verdict == "PASS" else ["Inert concrete finding"],
                        "summary": f"Inert cell {self.slot} {calls[-1][1]}",
                    }
                )
            )

    clients = {slot["slot_id"]: InertClient(slot["slot_id"]) for slot in slots}
    monkeypatch.setattr(pr_verifier, "_build_semantic_clients", lambda *_: [])
    # Only this offline test boundary supplies the authentication flag. No SDK,
    # credentials or genuine provider execution is claimed by the fixture.
    monkeypatch.setattr(
        pr_verifier, "_semantic_slots_and_clients", lambda *_: (slots, clients, True)
    )
    monkeypatch.setattr(
        pr_verifier,
        "_preflight_input_capacity",
        lambda _client, prompt: {
            "status": "PASS",
            "request_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "input_tokens": 1,
            "context_limit": 1000000,
            "output_reserve": 1000,
        },
    )
    run = pr_verifier._evaluate_pr_multiple_semantic(
        (fixture / "context.bin").read_text(), (fixture / "diff.bin").read_text(), None, None
    )
    payload = json.loads(
        json.dumps(
            {
                "results": [row.model_dump() for row in run],
                "semantic_acceptance": run.semantic_acceptance,
            }
        )
    )
    expected_count = 2 if single_package else 4
    assert len(calls) == expected_count and len(payload["results"]) == expected_count
    assert payload["semantic_acceptance"]["admission"]["verdict"] == verdict
    return payload


def _sign(payload):
    envelope = payload["semantic_acceptance"]
    envelope["signature"] = pr_verifier._semantic_envelope_signature(
        {k: v for k, v in envelope.items() if k != "signature"}
    )


@pytest.mark.parametrize(
    "case",
    [
        "complete",
        "missing_flat",
        "duplicate_flat",
        "foreign_flat",
        "missing_cell",
        "duplicate_cell",
        "foreign_cell",
        "missing_slot",
        "unavailable",
        "bad_signature",
    ],
)
def test_semantic_availability_uses_authenticated_complete_cell_matrix(semantic_payload, case):
    payload = semantic_payload
    envelope = payload["semantic_acceptance"]
    if case == "missing_flat":
        payload["results"].pop()
    elif case == "duplicate_flat":
        payload["results"][1] = dict(payload["results"][0])
    elif case == "foreign_flat":
        payload["results"][0]["provider_used"] = "foreign"
    elif case == "missing_cell":
        envelope["admission"]["results"].pop()
        _sign(payload)
    elif case == "duplicate_cell":
        envelope["admission"]["results"][1] = dict(envelope["admission"]["results"][0])
        _sign(payload)
    elif case == "foreign_cell":
        envelope["admission"]["results"][0]["slot_id"] = "foreign"
        _sign(payload)
    elif case == "missing_slot":
        envelope["execution"]["slots"].pop()
        _sign(payload)
    elif case == "unavailable":
        payload["results"][0]["used_llm"] = False
    elif case == "bad_signature":
        envelope["signature"] = "0" * 64
    rows, verdict, available = admission.validated_payload(payload, mode="compare")
    assert len(rows) == len(payload["results"])
    assert available is (case == "complete")
    assert verdict == ("CONCERNS" if case == "bad_signature" else "PASS")


def test_authored_semantic_compare_receipt_and_settlement_accept_four_real_producer_rows(
    semantic_payload, tmp_path, monkeypatch
):
    # Authored shell signs this inert producer payload with its actual ephemeral
    # invocation key; the unified path runs only after that key was retired.
    monkeypatch.delenv("VERIFIER_SEMANTIC_KEY_PATH")
    output = run_workflow(tmp_path, semantic_payload, semantic=True)
    receipt = json.loads((tmp_path / "comparison-execution.json").read_text())
    assert output["verdict"] == output["unified"] == "PASS"
    assert receipt["status"] == "completed" and receipt["decision_available"] is True
    assert len(json.loads((tmp_path / "comparison.json").read_text())["results"]) == 4


@pytest.mark.parametrize("semantic_payload", ["CONCERNS", "FAIL"], indirect=True)
def test_complete_semantic_nonpass_keeps_concrete_classifier_and_available_matrix(semantic_payload):
    rows, verdict, available = admission.validated_payload(semantic_payload, mode="compare")
    assert available is True and len(rows) == 4
    assert verdict == semantic_payload["semantic_acceptance"]["admission"]["verdict"]
    assert verdict in {"CONCERNS", "FAIL"}


@pytest.mark.parametrize("semantic_payload", ["single_package"], indirect=True)
def test_semantic_single_package_still_admits_the_complete_two_cell_matrix(semantic_payload):
    rows, verdict, available = admission.validated_payload(semantic_payload, mode="compare")
    assert available is True and verdict == "PASS" and len(rows) == 2
