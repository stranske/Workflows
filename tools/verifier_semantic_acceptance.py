"""Strict, source-owned semantic acceptance contracts for verifier packages.

This is deliberately a small validator, not an English-to-obligation splitter.
The caller supplies an already reviewed rule through a *separate* trusted rule
registry.  Captured JSON and provider responses can describe evidence, but can
never authorize a decomposition or a native execution receipt by themselves.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

RULE_SCHEMA = "workflows-verifier-semantic-rule/v1"
CONTRACT_SCHEMA = "workflows-verifier-semantic-contract/v1"
PLAN_SCHEMA = "workflows-verifier-semantic-package-plan/v1"
LEDGER_SCHEMA = "workflows-verifier-semantic-execution-ledger/v1"
_PREDICATES = frozenset({"equality", "set", "provenance", "bounds"})
_VERDICTS = frozenset({"PASS", "FAIL", "CONCERNS"})


def canonical_digest(value: Any) -> str:
    """Digest a value without allowing presentation changes to alter identity."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _is_hex(value: Any, size: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == size
        and all(c in "0123456789abcdef" for c in value)
    )


def _list_of_strings(value: Any, name: str, *, unique: bool = True) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{name} must be a list of nonempty strings")
    if unique and len(value) != len(set(value)):
        raise ValueError(f"{name} contains duplicates")
    return value


def _capture(capture: Any) -> dict[str, Any]:
    if not isinstance(capture, dict):
        raise ValueError("capture must be an object")
    if not isinstance(capture.get("id"), str) or not capture["id"]:
        raise ValueError("capture id is missing")
    if not _is_hex(capture.get("implementation_head"), 40):
        raise ValueError("capture implementation head is malformed")
    if not _is_hex(capture.get("governing_sha256"), 64):
        raise ValueError("capture governing hash is malformed")
    raw_inputs = capture.get("raw_inputs")
    if not isinstance(raw_inputs, dict) or not raw_inputs:
        raise ValueError("capture raw inputs are missing")
    if any(
        not isinstance(name, str) or not name or not _is_hex(digest, 64)
        for name, digest in raw_inputs.items()
    ):
        raise ValueError("capture raw input identity is malformed")
    _list_of_strings(capture.get("gaps"), "capture gaps")
    if type(capture.get("resource_admitted")) is not bool:
        raise ValueError("capture resource admission is malformed")
    return capture


def compile_contract(
    capture: dict[str, Any], rule: dict[str, Any], *, trusted_rule_digests: Iterable[str]
) -> dict[str, Any]:
    """Compile a reviewed rule only when a runtime-owned registry admits it.

    ``trusted_rule_digests`` must come from configuration or a trusted loader,
    never be deserialized from the capture or a provider result.
    """
    capture = _capture(capture)
    if not isinstance(rule, dict) or rule.get("schema") != RULE_SCHEMA:
        raise ValueError("semantic rule schema is unknown")
    digest = canonical_digest(rule)
    if digest not in set(trusted_rule_digests):
        raise ValueError("semantic rule is not in the trusted source-owned registry")
    if (
        rule.get("capture_id") != capture["id"]
        or rule.get("governing_sha256") != capture["governing_sha256"]
    ):
        raise ValueError("semantic rule does not bind the complete governing capture")
    clauses = rule.get("clauses")
    if not isinstance(clauses, list) or not clauses:
        raise ValueError("semantic rule has no clauses")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    raw_names = set(capture["raw_inputs"])
    for clause in clauses:
        if not isinstance(clause, dict):
            raise ValueError("semantic clause is malformed")
        clause_id = clause.get("id")
        if not isinstance(clause_id, str) or not clause_id or clause_id in seen:
            raise ValueError("semantic clause id is missing or duplicate")
        seen.add(clause_id)
        predicate = clause.get("predicate")
        if predicate not in _PREDICATES:
            raise ValueError("semantic clause predicate is not allowlisted")
        dependencies = _list_of_strings(clause.get("raw_dependencies"), "raw dependencies")
        if not set(dependencies) <= raw_names:
            raise ValueError("semantic clause has an unknown raw dependency")
        requires = _list_of_strings(clause.get("requires", []), "clause requirements")
        groups = _list_of_strings(clause.get("joint_groups", []), "joint groups")
        residual = clause.get("residual", False)
        if type(residual) is not bool:
            raise ValueError("semantic residual marker is malformed")
        if residual and set(dependencies) != raw_names:
            raise ValueError("residual obligations must retain all captured inputs")
        normalized.append(
            {
                "id": clause_id,
                "predicate": predicate,
                "raw_dependencies": sorted(dependencies),
                "requires": sorted(requires),
                "joint_groups": sorted(groups),
                "residual": residual,
            }
        )
    if any(requirement not in seen for clause in normalized for requirement in clause["requires"]):
        raise ValueError("semantic clause requirement is unresolved")
    # Every input needs explicit coverage. Unknown governing text must be made a
    # residual clause by the trusted rule owner, never guessed here.
    if set().union(*(set(item["raw_dependencies"]) for item in normalized)) != raw_names:
        raise ValueError("semantic rule leaves captured inputs without an obligation")
    contract = {
        "schema": CONTRACT_SCHEMA,
        "capture_id": capture["id"],
        "implementation_head": capture["implementation_head"],
        "governing_sha256": capture["governing_sha256"],
        "raw_inputs": dict(sorted(capture["raw_inputs"].items())),
        "capture_gaps": list(capture["gaps"]),
        "resource_admitted": capture["resource_admitted"],
        "rule_sha256": digest,
        "clauses": sorted(normalized, key=lambda item: item["id"]),
    }
    contract["id"] = canonical_digest(contract)
    return contract


def build_package_plan(contract: dict[str, Any], packages: list[dict[str, Any]]) -> dict[str, Any]:
    """Require each package to contain the complete dependency and joint closure."""
    if not isinstance(contract, dict) or contract.get("schema") != CONTRACT_SCHEMA:
        raise ValueError("semantic contract is unknown")
    clauses = {item["id"]: item for item in contract.get("clauses", [])}
    if not clauses or not isinstance(packages, list) or not packages:
        raise ValueError("semantic package plan is empty")
    by_group: dict[str, set[str]] = defaultdict(set)
    for clause in clauses.values():
        for group in clause["joint_groups"]:
            by_group[group].add(clause["id"])
    all_inputs = set(contract["raw_inputs"])
    planned: list[dict[str, Any]] = []
    seen_packages: set[str] = set()
    assigned: set[str] = set()
    for package in packages:
        if (
            not isinstance(package, dict)
            or not isinstance(package.get("id"), str)
            or not package["id"]
            or package["id"] in seen_packages
        ):
            raise ValueError("semantic package id is missing or duplicate")
        seen_packages.add(package["id"])
        clause_ids = set(_list_of_strings(package.get("clause_ids"), "package clause ids"))
        if not clause_ids <= set(clauses) or assigned & clause_ids:
            raise ValueError("semantic package has unknown or duplicate clauses")
        assigned |= clause_ids
        inputs = set(_list_of_strings(package.get("raw_inputs"), "package raw inputs"))
        if not inputs <= all_inputs:
            raise ValueError("semantic package has an unknown raw input")
        closure = set(clause_ids)
        changed = True
        while changed:
            changed = False
            for clause_id in list(closure):
                before = len(closure)
                closure.update(clauses[clause_id]["requires"])
                for group in clauses[clause_id]["joint_groups"]:
                    closure.update(by_group[group])
                changed |= len(closure) != before
        if closure != clause_ids:
            raise ValueError("semantic package is missing dependency or n-way joint closure")
        needed_inputs = set().union(*(set(clauses[item]["raw_dependencies"]) for item in closure))
        if inputs != needed_inputs:
            raise ValueError("semantic package raw dependency closure is incomplete")
        planned.append(
            {
                "id": package["id"],
                "clause_ids": sorted(clause_ids),
                "raw_inputs": sorted(inputs),
                "closure_sha256": canonical_digest(
                    {"clauses": sorted(clause_ids), "raw_inputs": sorted(inputs)}
                ),
            }
        )
    if assigned != set(clauses):
        raise ValueError("semantic package plan does not cover every clause")
    plan = {
        "schema": PLAN_SCHEMA,
        "contract_id": contract["id"],
        "packages": sorted(planned, key=lambda item: item["id"]),
    }
    plan["id"] = canonical_digest(plan)
    return plan


def validate_reassembly(
    capture: dict[str, Any], contract: dict[str, Any], plan: dict[str, Any]
) -> None:
    """Recheck capture identity and exact closure before a real provider call."""
    capture = _capture(capture)
    if (
        contract.get("capture_id") != capture["id"]
        or contract.get("implementation_head") != capture["implementation_head"]
        or contract.get("governing_sha256") != capture["governing_sha256"]
        or contract.get("raw_inputs") != dict(sorted(capture["raw_inputs"].items()))
    ):
        raise ValueError("capture no longer matches the semantic contract")
    rebuilt = build_package_plan(
        contract,
        [
            {"id": item["id"], "clause_ids": item["clause_ids"], "raw_inputs": item["raw_inputs"]}
            for item in plan.get("packages", [])
        ],
    )
    if canonical_digest(rebuilt) != canonical_digest(plan):
        raise ValueError("semantic package plan was changed after closure validation")


def freeze_judge_slots(slots: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Freeze required judges before availability filtering or provider lookup."""
    frozen: list[dict[str, Any]] = []
    ids: set[str] = set()
    for slot in slots:
        if not isinstance(slot, dict):
            raise ValueError("judge slot is malformed")
        values = [slot.get(field) for field in ("slot_id", "provider", "model", "transport")]
        if (
            any(not isinstance(value, str) or not value for value in values)
            or slot["slot_id"] in ids
            or not _is_hex(slot.get("config_sha256"), 64)
        ):
            raise ValueError("judge slot identity is malformed or duplicate")
        ids.add(slot["slot_id"])
        frozen.append(
            {
                field: slot[field]
                for field in ("slot_id", "provider", "model", "transport", "config_sha256")
            }
        )
    if not frozen:
        raise ValueError("at least one judge slot is required")
    return tuple(sorted(frozen, key=lambda item: item["slot_id"]))


def plan_request_matrix(plan: dict[str, Any], slots: list[dict[str, Any]]) -> set[tuple[str, str]]:
    if plan.get("schema") != PLAN_SCHEMA:
        raise ValueError("semantic package plan is unknown")
    frozen = freeze_judge_slots(slots)
    return {(slot["slot_id"], package["id"]) for slot in frozen for package in plan["packages"]}


def validate_proof_chain(
    chain: dict[str, Any], trusted_receipts: dict[str, dict[str, Any]]
) -> None:
    """Validate selected-test RED/restored-GREEN facts from trusted execution receipts."""
    if not isinstance(chain, dict) or not isinstance(trusted_receipts, dict):
        raise ValueError("proof chain is malformed")
    for name in (
        "original_sha256",
        "mutant_sha256",
        "restored_sha256",
        "red_receipt",
        "green_receipt",
    ):
        if name not in chain:
            raise ValueError("proof chain is incomplete")
    if chain["original_sha256"] != chain["restored_sha256"]:
        raise ValueError("proof restoration is not byte-identical")
    red, green = (trusted_receipts.get(chain[key]) for key in ("red_receipt", "green_receipt"))
    if not isinstance(red, dict) or not isinstance(green, dict):
        raise ValueError("proof receipt is not trusted")
    selected = _list_of_strings(chain.get("selected_tests"), "selected tests")
    if (
        red.get("selected_tests") != selected
        or green.get("selected_tests") != selected
        or red.get("exit_code") != 1
        or green.get("exit_code") != 0
        or red.get("assertion_failure") is not True
        or green.get("errors")
        or green.get("skipped")
    ):
        raise ValueError("proof chain does not show selected assertion RED and restored GREEN")


def admit_results(
    capture: dict[str, Any],
    contract: dict[str, Any],
    plan: dict[str, Any],
    expected_cells: set[tuple[str, str]],
    results: list[dict[str, Any]],
    ledger: dict[str, Any],
    *,
    trusted_ledger_digests: Iterable[str],
) -> dict[str, Any]:
    """Admit an exact, runner-bound result matrix while retaining all defects."""
    validate_reassembly(capture, contract, plan)
    if (
        not isinstance(ledger, dict)
        or ledger.get("schema") != LEDGER_SCHEMA
        or canonical_digest(ledger) not in set(trusted_ledger_digests)
    ):
        raise ValueError("execution ledger is not supplied by the trusted runner")
    if (
        ledger.get("capture_id") != contract["capture_id"]
        or ledger.get("contract_id") != contract["id"]
        or ledger.get("plan_id") != plan["id"]
    ):
        raise ValueError("execution ledger does not bind this capture, contract, and package plan")
    receipts = ledger.get("cells")
    if not isinstance(receipts, list):
        raise ValueError("execution ledger cells are malformed")
    receipt_by_cell: dict[tuple[str, str], dict[str, Any]] = {}
    bound_receipts: dict[tuple[str, str], dict[str, Any]] = {}
    errors: list[str] = []
    for receipt in receipts:
        if not isinstance(receipt, dict):
            errors.append("malformed trusted receipt")
            continue
        slot_id, package_id = receipt.get("slot_id"), receipt.get("package_id")
        if (
            not isinstance(slot_id, str)
            or not slot_id
            or not isinstance(package_id, str)
            or not package_id
        ):
            errors.append("invalid trusted receipt")
            continue
        cell = (slot_id, package_id)
        if (
            cell in bound_receipts
            or not _is_hex(receipt.get("request_sha256"), 64)
            or not _is_hex(receipt.get("response_sha256"), 64)
            or not _is_hex(receipt.get("result_sha256"), 64)
        ):
            errors.append("invalid trusted receipt")
            continue
        bound_receipts[cell] = receipt
        if receipt.get("completed") is not True or receipt.get("synthetic") is not False:
            errors.append("non-native or incomplete trusted receipt")
            continue
        receipt_by_cell[cell] = receipt
    result_by_cell: dict[tuple[str, str], dict[str, Any]] = {}
    package_clauses = {item["id"]: item["clause_ids"] for item in plan["packages"]}
    findings: list[Any] = []
    for result in results:
        if not isinstance(result, dict):
            errors.append("malformed provider result")
            continue
        slot_id, package_id = result.get("slot_id"), result.get("package_id")
        if (
            not isinstance(slot_id, str)
            or not slot_id
            or not isinstance(package_id, str)
            or not package_id
        ):
            errors.append("invalid provider result")
            continue
        cell = (slot_id, package_id)
        if (
            cell in result_by_cell
            or cell not in expected_cells
            or result.get("verdict") not in _VERDICTS
            or not isinstance(result.get("findings", []), list)
            or result.get("clause_ids") != package_clauses.get(cell[1])
            or canonical_digest(result) != bound_receipts.get(cell, {}).get("result_sha256")
        ):
            errors.append("invalid provider result")
            continue
        result_by_cell[cell] = result
        findings.extend(result["findings"])
    missing = sorted(expected_cells - set(result_by_cell))
    if set(receipt_by_cell) != expected_cells:
        errors.append("trusted execution matrix is incomplete or has extra cells")
    valid_fail = any(
        result.get("verdict") == "FAIL" and cell in receipt_by_cell
        for cell, result in result_by_cell.items()
    )
    concerns = (
        bool(capture["gaps"])
        or not capture["resource_admitted"]
        or bool(missing)
        or bool(errors)
        or bool(findings)
        or any(result["verdict"] != "PASS" for result in result_by_cell.values())
    )
    verdict = "FAIL" if valid_fail else ("CONCERNS" if concerns else "PASS")
    return {
        "verdict": verdict,
        "expected_cells": sorted(expected_cells),
        "missing_cells": missing,
        "findings": findings,
        "errors": errors,
        "results": results,
    }
