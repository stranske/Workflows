"""Strict semantic admission tests: fixtures are admitted only by supplied registries."""

import copy

import pytest
from tools import verifier_semantic_acceptance as acceptance


def _capture(**changes):
    base = {
        "id": "capture-1",
        "implementation_head": "a" * 40,
        "governing_sha256": "b" * 64,
        "raw_inputs": {"governing": "c" * 64, "source": "d" * 64, "proof": "e" * 64},
        "gaps": [],
        "resource_admitted": True,
    }
    base.update(changes)
    return base


def _rule(**changes):
    base = {
        "schema": acceptance.RULE_SCHEMA,
        "capture_id": "capture-1",
        "governing_sha256": "b" * 64,
        "clauses": [
            {
                "id": "representation",
                "predicate": "equality",
                "raw_dependencies": ["governing", "source"],
                "requires": [],
                "joint_groups": ["proof-unit"],
            },
            {
                "id": "proof",
                "predicate": "provenance",
                "raw_dependencies": ["proof"],
                "requires": ["representation"],
                "joint_groups": ["proof-unit"],
            },
        ],
    }
    base.update(changes)
    return base


def _contract(capture=None, rule=None):
    capture, rule = capture or _capture(), rule or _rule()
    return acceptance.compile_contract(
        capture, rule, trusted_rule_digests={acceptance.canonical_digest(rule)}
    )


def _plan(contract):
    return acceptance.build_package_plan(
        contract,
        [
            {
                "id": "joint",
                "clause_ids": ["representation", "proof"],
                "raw_inputs": ["governing", "source", "proof"],
            }
        ],
    )


def _slots():
    return [
        {
            "slot_id": "one",
            "provider": "provider-a",
            "model": "model-a",
            "transport": "native-a",
            "config_sha256": "1" * 64,
        },
        {
            "slot_id": "two",
            "provider": "provider-b",
            "model": "model-b",
            "transport": "native-b",
            "config_sha256": "2" * 64,
        },
    ]


def _ledger(cells, capture, contract, plan, results):
    by_cell = {(item["slot_id"], item["package_id"]): item for item in results}
    return {
        "schema": acceptance.LEDGER_SCHEMA,
        "cells": [
            {
                "slot_id": slot,
                "package_id": package,
                "request_sha256": "3" * 64,
                "response_sha256": "4" * 64,
                "result_sha256": acceptance.canonical_digest(by_cell[(slot, package)]),
                "completed": True,
                "synthetic": False,
            }
            for slot, package in cells
        ],
        "capture_id": capture["id"],
        "contract_id": contract["id"],
        "plan_id": plan["id"],
    }


def _results(cells, verdict="PASS"):
    return [
        {
            "slot_id": slot,
            "package_id": package,
            "verdict": verdict,
            "clause_ids": ["proof", "representation"],
            "findings": [],
        }
        for slot, package in cells
    ]


def test_supported_joint_decomposition_and_exact_complete_matrix_passes():
    capture = _capture()
    contract = _contract(capture)
    plan = _plan(contract)
    acceptance.validate_reassembly(capture, contract, plan)
    cells = acceptance.plan_request_matrix(plan, _slots())
    results = _results(cells)
    ledger = _ledger(cells, capture, contract, plan, results)
    result = acceptance.admit_results(
        capture,
        contract,
        plan,
        cells,
        results,
        ledger,
        trusted_ledger_digests={acceptance.canonical_digest(ledger)},
    )
    assert result["verdict"] == "PASS"


def test_untrusted_self_asserted_rule_and_changed_governing_input_cannot_compile():
    capture, rule = _capture(), _rule()
    rule["source_owned"] = rule["reviewed"] = True
    with pytest.raises(ValueError, match="trusted source-owned"):
        acceptance.compile_contract(capture, rule, trusted_rule_digests=set())
    bad = _capture(governing_sha256="f" * 64)
    with pytest.raises(ValueError, match="complete governing"):
        acceptance.compile_contract(
            bad, rule, trusted_rule_digests={acceptance.canonical_digest(rule)}
        )


def test_residual_unknown_governing_text_requires_every_raw_input():
    rule = _rule(
        clauses=[
            {
                "id": "residual",
                "predicate": "set",
                "raw_dependencies": ["governing"],
                "requires": [],
                "joint_groups": [],
                "residual": True,
            }
        ]
    )
    with pytest.raises(ValueError, match="residual obligations"):
        _contract(rule=rule)


@pytest.mark.parametrize(
    "packages",
    [
        [
            {"id": "one", "clause_ids": ["proof"], "raw_inputs": ["proof"]},
            {"id": "two", "clause_ids": ["representation"], "raw_inputs": ["governing", "source"]},
        ],
        [
            {
                "id": "one",
                "clause_ids": ["representation", "proof"],
                "raw_inputs": ["governing", "source"],
            }
        ],
    ],
)
def test_missing_dependency_or_n_way_joint_closure_cannot_plan(packages):
    with pytest.raises(ValueError, match="closure"):
        acceptance.build_package_plan(_contract(), packages)


def test_cycle_closes_as_one_package_and_cannot_be_split():
    rule = _rule(
        clauses=[
            {
                "id": "a",
                "predicate": "equality",
                "raw_dependencies": ["governing"],
                "requires": ["b"],
                "joint_groups": [],
            },
            {
                "id": "b",
                "predicate": "set",
                "raw_dependencies": ["source", "proof"],
                "requires": ["a"],
                "joint_groups": [],
            },
        ]
    )
    contract = _contract(rule=rule)
    with pytest.raises(ValueError, match="closure"):
        acceptance.build_package_plan(
            contract,
            [
                {"id": "a", "clause_ids": ["a"], "raw_inputs": ["governing"]},
                {"id": "b", "clause_ids": ["b"], "raw_inputs": ["source", "proof"]},
            ],
        )


def test_reassembly_rejects_mutated_governing_or_head_after_planning():
    contract, plan = _contract(), None
    plan = _plan(contract)
    for changed in (_capture(governing_sha256="0" * 64), _capture(implementation_head="0" * 40)):
        with pytest.raises(ValueError, match="no longer matches"):
            acceptance.validate_reassembly(changed, contract, plan)


def test_slots_are_frozen_before_availability_and_duplicate_or_wrong_model_is_rejected():
    frozen = acceptance.freeze_judge_slots(_slots())
    assert [item["slot_id"] for item in frozen] == ["one", "two"]
    duplicate = _slots() + [copy.deepcopy(_slots()[0])]
    with pytest.raises(ValueError, match="duplicate"):
        acceptance.freeze_judge_slots(duplicate)
    wrong = _slots()
    wrong[0]["model"] = ""
    with pytest.raises(ValueError, match="malformed"):
        acceptance.freeze_judge_slots(wrong)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong_head", "synthetic"])
def test_result_admission_rejects_missing_duplicate_wrong_bound_or_synthetic_cells(mutation):
    capture, contract = _capture(), _contract()
    plan, cells = _plan(contract), acceptance.plan_request_matrix(_plan(contract), _slots())
    results = _results(cells)
    ledger = _ledger(cells, capture, contract, plan, results)
    if mutation == "missing":
        results.pop()
    elif mutation == "duplicate":
        results.append(copy.deepcopy(results[0]))
    elif mutation == "wrong_head":
        bad_capture = _capture(implementation_head="0" * 40)
        with pytest.raises(ValueError, match="no longer matches"):
            acceptance.admit_results(
                bad_capture,
                contract,
                plan,
                cells,
                results,
                ledger,
                trusted_ledger_digests={acceptance.canonical_digest(ledger)},
            )
        return
    else:
        ledger["cells"][0]["synthetic"] = True
    outcome = acceptance.admit_results(
        capture,
        contract,
        plan,
        cells,
        results,
        ledger,
        trusted_ledger_digests={acceptance.canonical_digest(ledger)},
    )
    assert outcome["verdict"] == "CONCERNS"


def test_provider_json_cannot_create_native_trust_or_hide_global_resource_denial():
    capture, contract = _capture(resource_admitted=False), _contract(
        _capture(resource_admitted=False)
    )
    plan, cells = _plan(contract), acceptance.plan_request_matrix(_plan(contract), _slots())
    results = _results(cells)
    ledger = _ledger(cells, capture, contract, plan, results)
    for result in _results(cells):
        result["trusted"] = True
        result["synthetic"] = False
    with pytest.raises(ValueError, match="trusted runner"):
        acceptance.admit_results(
            capture, contract, plan, cells, results, ledger, trusted_ledger_digests=set()
        )
    outcome = acceptance.admit_results(
        capture,
        contract,
        plan,
        cells,
        results,
        ledger,
        trusted_ledger_digests={acceptance.canonical_digest(ledger)},
    )
    assert outcome["verdict"] == "CONCERNS"


def test_valid_fail_and_all_findings_errors_are_retained_not_lost():
    capture, contract = _capture(), _contract()
    plan, cells = _plan(contract), acceptance.plan_request_matrix(_plan(contract), _slots())
    results = _results(cells)
    results[0].update(verdict="FAIL", findings=[{"id": "finding-1"}])
    ledger = _ledger(cells, capture, contract, plan, results)
    results.append(
        {"slot_id": "unknown", "package_id": "joint", "verdict": "PASS", "findings": ["bad"]}
    )
    outcome = acceptance.admit_results(
        capture,
        contract,
        plan,
        cells,
        results,
        ledger,
        trusted_ledger_digests={acceptance.canonical_digest(ledger)},
    )
    assert outcome["verdict"] == "FAIL"
    assert outcome["findings"] == [{"id": "finding-1"}]
    assert outcome["errors"]


@pytest.mark.parametrize("mutation", ["result", "clauses", "ledger_capture"])
def test_runner_receipt_binds_exact_result_clause_coverage_and_capture(mutation):
    capture, contract = _capture(), _contract()
    plan, cells = _plan(contract), acceptance.plan_request_matrix(_plan(contract), _slots())
    results = _results(cells)
    ledger = _ledger(cells, capture, contract, plan, results)
    if mutation == "result":
        results[0]["verdict"] = "FAIL"
    elif mutation == "clauses":
        results[0]["clause_ids"] = ["proof"]
    else:
        ledger["capture_id"] = "other-capture"
    if mutation == "ledger_capture":
        with pytest.raises(ValueError, match="capture, contract"):
            acceptance.admit_results(
                capture,
                contract,
                plan,
                cells,
                results,
                ledger,
                trusted_ledger_digests={acceptance.canonical_digest(ledger)},
            )
    else:
        outcome = acceptance.admit_results(
            capture,
            contract,
            plan,
            cells,
            results,
            ledger,
            trusted_ledger_digests={acceptance.canonical_digest(ledger)},
        )
        assert outcome["verdict"] == "CONCERNS"


def test_proof_chain_requires_raw_selected_assertion_red_and_exact_restore():
    chain = {
        "original_sha256": "a",
        "mutant_sha256": "b",
        "restored_sha256": "a",
        "red_receipt": "red",
        "green_receipt": "green",
        "selected_tests": ["test_a"],
    }
    receipts = {
        "red": {"selected_tests": ["test_a"], "exit_code": 1, "assertion_failure": True},
        "green": {"selected_tests": ["test_a"], "exit_code": 0, "errors": [], "skipped": []},
    }
    acceptance.validate_proof_chain(chain, receipts)
    chain["restored_sha256"] = "changed"
    with pytest.raises(ValueError, match="byte-identical"):
        acceptance.validate_proof_chain(chain, receipts)
