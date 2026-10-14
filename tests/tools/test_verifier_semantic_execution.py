"""Execution boundary tests use callbacks only; no provider is contacted."""

from __future__ import annotations

import pytest
from tools.verifier_semantic_execution import SourceRuleRegistry, execute_semantic_matrix


def _capture():
    return {
        "id": "capture",
        "implementation_head": "a" * 40,
        "governing_sha256": "b" * 64,
        "raw_inputs": {"governing": "c" * 64, "source": "d" * 64},
        "gaps": [],
        "resource_admitted": True,
    }


def _rule():
    return {
        "schema": "workflows-verifier-semantic-rule/v1",
        "capture_id": "capture",
        "governing_sha256": "b" * 64,
        "clauses": [
            {
                "id": "review",
                "predicate": "equality",
                "raw_dependencies": ["governing", "source"],
                "requires": [],
                "joint_groups": [],
            }
        ],
    }


def _packages():
    return [{"id": "whole", "clause_ids": ["review"], "raw_inputs": ["governing", "source"]}]


def _slots():
    return [
        {
            "slot_id": "a",
            "provider": "one",
            "model": "m1",
            "transport": "native",
            "config_sha256": "1" * 64,
        },
        {
            "slot_id": "b",
            "provider": "two",
            "model": "m2",
            "transport": "native",
            "config_sha256": "2" * 64,
        },
    ]


def _loader(rule=None):
    registry = SourceRuleRegistry({("capture", "b" * 64): rule or _rule()})
    return registry.load


def _request(slot, package, contract):
    return {"slot": slot["slot_id"], "package": package["id"], "contract": contract["id"]}


def _preflight(slot, package, request):
    from tools.verifier_semantic_acceptance import canonical_digest

    return {
        "accepted": True,
        "request_sha256": canonical_digest(request),
        "input_tokens": 10,
        "context_limit": 100,
        "output_reserve": 20,
    }


def _parse(raw, slot, package):
    return {"verdict": "PASS", "findings": []}


def test_freezes_and_preflights_entire_matrix_before_first_native_invoke():
    events = []

    def preflight(slot, package, request):
        events.append(("preflight", slot["slot_id"]))
        return _preflight(slot, package, request)

    def invoke(slot, request):
        assert events[:2] == [("preflight", "a"), ("preflight", "b")]
        events.append(("invoke", slot["slot_id"]))
        return "{}"

    run = execute_semantic_matrix(
        _capture(),
        _loader(),
        _packages(),
        _slots(),
        _request,
        preflight,
        invoke,
        _parse,
        authenticated_native=True,
    )
    assert events == [("preflight", "a"), ("preflight", "b"), ("invoke", "a"), ("invoke", "b")]
    assert run.admit()["verdict"] == "PASS"


def test_any_preflight_failure_stops_before_any_native_invoke():
    invoked = []

    def preflight(slot, package, request):
        facts = _preflight(slot, package, request)
        if slot["slot_id"] == "b":
            facts["accepted"] = False
        return facts

    with pytest.raises(ValueError, match="preflight"):
        execute_semantic_matrix(
            _capture(),
            _loader(),
            _packages(),
            _slots(),
            _request,
            preflight,
            lambda *args: invoked.append(args),
            _parse,
            authenticated_native=True,
        )
    assert invoked == []


def test_test_execution_is_synthetic_and_can_never_admit_pass():
    run = execute_semantic_matrix(
        _capture(),
        _loader(),
        _packages(),
        _slots(),
        _request,
        _preflight,
        lambda *args: "{}",
        _parse,
        authenticated_native=False,
    )
    assert run.admit()["verdict"] == "CONCERNS"
    assert all(cell["synthetic"] for cell in run.ledger["cells"])


def test_native_error_is_retained_without_retry_or_fallback():
    calls = []

    def invoke(slot, request):
        calls.append(slot["slot_id"])
        if slot["slot_id"] == "a":
            raise RuntimeError("transport failure")
        return "{}"

    run = execute_semantic_matrix(
        _capture(),
        _loader(),
        _packages(),
        _slots(),
        _request,
        _preflight,
        invoke,
        _parse,
        authenticated_native=True,
    )
    admission = run.admit()
    assert calls == ["a", "b"]
    assert admission["verdict"] == "CONCERNS"
    assert any(
        not item["completed"] and item["error"] == "transport failure"
        for item in run.ledger["cells"]
    )


def test_registry_rejects_capture_supplied_authority_and_unknown_text_needs_all_input_residual_package():
    capture = _capture()
    capture["source_owned"] = capture["reviewed"] = True
    registry = SourceRuleRegistry({})
    with pytest.raises(ValueError, match="no source-owned"):
        registry.load(capture)
    registry = SourceRuleRegistry({("capture", "b" * 64): _rule()})
    rule, digest = registry.load(capture, unknown_governing_text=True)
    residual = rule["clauses"][-1]
    assert residual["residual"] is True and residual["raw_dependencies"] == ["governing", "source"]
    specs = [
        {
            "id": "residual-joint",
            "clause_ids": ["review", "__unknown_governing_residual__"],
            "raw_inputs": ["governing", "source"],
        }
    ]
    run = execute_semantic_matrix(
        capture,
        lambda _: (rule, digest),
        specs,
        _slots(),
        _request,
        _preflight,
        lambda *args: "{}",
        _parse,
        authenticated_native=False,
    )
    assert {package["id"] for package in run.plan["packages"]} == {"residual-joint"}


def test_preflight_must_bind_exact_serialized_request():
    def bad_preflight(slot, package, request):
        facts = _preflight(slot, package, request)
        facts["request_sha256"] = "0" * 64
        return facts

    with pytest.raises(ValueError, match="exact request"):
        execute_semantic_matrix(
            _capture(),
            _loader(),
            _packages(),
            _slots(),
            _request,
            bad_preflight,
            lambda *args: "{}",
            _parse,
            authenticated_native=True,
        )
