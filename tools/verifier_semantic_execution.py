"""Native-only execution boundary for semantic verifier packages.

The caller owns real provider adapters.  This module freezes the complete
slot/package matrix and obtains capacity facts for every request before making
the first invocation.  It deliberately does not retry, substitute models, or
repair a response schema.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass
from time import monotonic
from typing import Any

from tools.verifier_semantic_acceptance import (
    LEDGER_SCHEMA,
    RULE_SCHEMA,
    admit_results,
    build_package_plan,
    canonical_digest,
    compile_contract,
    freeze_judge_slots,
    plan_request_matrix,
)

MAX_NATIVE_CELLS = 16
MAX_NATIVE_SECONDS = 1200


@dataclass(frozen=True)
class SourceRuleRegistry:
    """Runtime-owned reviewed-rule registry keyed by exact capture identity."""

    rules: dict[tuple[str, str], dict[str, Any]]

    def load(
        self, capture: dict[str, Any], *, unknown_governing_text: bool = False
    ) -> tuple[dict[str, Any], set[str]]:
        key = (capture.get("id"), capture.get("governing_sha256"))
        if key not in self.rules:
            raise ValueError("no source-owned reviewed rule matches this capture")
        rule = deepcopy(self.rules[key])
        if rule.get("schema") != RULE_SCHEMA:
            raise ValueError("source-owned registry contains an invalid rule")
        if unknown_governing_text:
            _add_residual_all_input_clause(rule, capture)
        return rule, {canonical_digest(rule)}


def _add_residual_all_input_clause(rule: dict[str, Any], capture: dict[str, Any]) -> None:
    """Force unknown governing text into one all-input joint obligation."""
    clauses = rule.get("clauses")
    if not isinstance(clauses, list):
        raise ValueError("source-owned rule has no clauses")
    if any(
        item.get("id") == "__unknown_governing_residual__"
        for item in clauses
        if isinstance(item, dict)
    ):
        return
    existing = [
        item.get("id")
        for item in clauses
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    clauses.append(
        {
            "id": "__unknown_governing_residual__",
            "predicate": "provenance",
            "raw_dependencies": sorted(capture["raw_inputs"]),
            "requires": existing,
            "joint_groups": ["__unknown_governing_joint__"],
            "residual": True,
        }
    )


@dataclass(frozen=True)
class SemanticExecution:
    """Runner-created values, suitable for immediate integration by the caller."""

    capture: dict[str, Any]
    contract: dict[str, Any]
    plan: dict[str, Any]
    slots: tuple[dict[str, Any], ...]
    expected_cells: set[tuple[str, str]]
    results: list[dict[str, Any]]
    ledger: dict[str, Any]
    ledger_digest: str

    def admit(self) -> dict[str, Any]:
        return admit_results(
            self.capture,
            self.contract,
            self.plan,
            self.expected_cells,
            self.results,
            self.ledger,
            trusted_ledger_digests={self.ledger_digest},
        )


def _valid_preflight(facts: Any, request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(facts, dict) or facts.get("accepted") is not True:
        raise ValueError("native capacity preflight did not admit the request")
    if facts.get("request_sha256") != canonical_digest(request):
        raise ValueError("native capacity preflight was not bound to the exact request")
    for name in ("input_tokens", "context_limit", "output_reserve"):
        if type(facts.get(name)) is not int or facts[name] < 0:
            raise ValueError("native capacity preflight facts are malformed")
    bound = {
        name: facts[name]
        for name in ("request_sha256", "input_tokens", "context_limit", "output_reserve")
    }
    if "native_payload_sha256" in facts:
        digest = facts["native_payload_sha256"]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise ValueError("native payload identity is malformed")
        bound["native_payload_sha256"] = digest
    return bound


def execute_semantic_matrix(
    capture: dict[str, Any],
    rule_loader: Callable[[dict[str, Any]], tuple[dict[str, Any], Iterable[str]]],
    package_specs: list[dict[str, Any]],
    slots: list[dict[str, Any]],
    build_request: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]],
    preflight_request: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]],
    invoke_native: Callable[[dict[str, Any], dict[str, Any]], str | bytes],
    parse_response: Callable[[str | bytes, dict[str, Any], dict[str, Any]], dict[str, Any]],
    *,
    authenticated_native: bool,
) -> SemanticExecution:
    """Preflight all frozen cells, then invoke each exactly once without repair.

    ``preflight_request`` is where the parent calls `_prepare_capacity_client`
    and `_preflight_input_capacity`; it must return native count facts bound to
    the serialized request.  A test run may exercise this routine, but cannot
    yield PASS because ``authenticated_native`` remains false.
    """
    rule, trusted_rule_digests = rule_loader(capture)
    contract = compile_contract(capture, rule, trusted_rule_digests=trusted_rule_digests)
    plan = build_package_plan(contract, package_specs)
    frozen_slots = freeze_judge_slots(slots)
    expected_cells = plan_request_matrix(plan, list(frozen_slots))
    if len(expected_cells) > MAX_NATIVE_CELLS:
        raise ValueError("semantic native matrix exceeds the finite cell bound")
    deadline = monotonic() + MAX_NATIVE_SECONDS

    def check_deadline() -> None:
        if monotonic() >= deadline:
            raise ValueError("semantic native execution elapsed bound exhausted")

    if capture["gaps"] or not capture["resource_admitted"]:
        ledger = {
            "schema": LEDGER_SCHEMA,
            "capture_id": contract["capture_id"],
            "contract_id": contract["id"],
            "plan_id": plan["id"],
            "cells": [],
        }
        return SemanticExecution(
            capture,
            contract,
            plan,
            frozen_slots,
            expected_cells,
            [],
            ledger,
            canonical_digest(ledger),
        )
    packages = {item["id"]: item for item in plan["packages"]}
    slot_by_id = {item["slot_id"]: item for item in frozen_slots}

    prepared: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
    # This whole loop completes before invoke_native appears below.
    for slot_id, package_id in sorted(expected_cells):
        check_deadline()
        slot, package = slot_by_id[slot_id], packages[package_id]
        request = build_request(slot, package, contract)
        if not isinstance(request, dict):
            raise ValueError("native request builder did not return an object")
        prepared[(slot_id, package_id)] = (
            request,
            _valid_preflight(preflight_request(slot, package, request), request),
        )
        check_deadline()

    results: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for slot_id, package_id in sorted(expected_cells):
        slot, package = slot_by_id[slot_id], packages[package_id]
        request, counts = prepared[(slot_id, package_id)]
        raw_response = None
        try:
            check_deadline()
            raw_response = invoke_native(slot, request)
            check_deadline()
            if not isinstance(raw_response, (str, bytes)):
                raise ValueError("native adapter returned a non-text response")
            parsed = parse_response(raw_response, slot, package)
            if not isinstance(parsed, dict):
                raise ValueError("response parser returned a non-object")
            parsed = dict(parsed)
            parsed["slot_id"], parsed["package_id"] = slot_id, package_id
            parsed.setdefault("findings", [])
            # Clause coverage is attached by the trusted runner after a
            # production response was parsed for the complete package, never
            # accepted as a provider-supplied self-assertion.
            parsed["clause_ids"] = list(package["clause_ids"])
            results.append(parsed)
            receipts.append(
                {
                    "slot_id": slot_id,
                    "package_id": package_id,
                    "request_sha256": counts["request_sha256"],
                    "response_sha256": canonical_digest(
                        {
                            "raw": (
                                raw_response.decode()
                                if isinstance(raw_response, bytes)
                                else raw_response
                            )
                        }
                    ),
                    "result_sha256": canonical_digest(parsed),
                    "completed": True,
                    "synthetic": not authenticated_native,
                    "counts": counts,
                }
            )
        except Exception as error:  # A failed cell is evidence; never retry or replace it.
            detail = (
                raw_response.decode("utf-8", errors="replace")
                if isinstance(raw_response, bytes)
                else raw_response if isinstance(raw_response, str) else None
            )
            failed_result = {
                "slot_id": slot_id,
                "package_id": package_id,
                "clause_ids": list(package["clause_ids"]),
                "verdict": "CONCERNS",
                "findings": [],
                "execution_error": str(error),
                "raw_content": detail,
            }
            results.append(failed_result)
            receipts.append(
                {
                    "slot_id": slot_id,
                    "package_id": package_id,
                    "request_sha256": counts["request_sha256"],
                    "response_sha256": (
                        canonical_digest({"raw": detail}) if detail is not None else "0" * 64
                    ),
                    "result_sha256": canonical_digest(failed_result),
                    "completed": False,
                    "synthetic": not authenticated_native,
                    "counts": counts,
                    "error": str(error),
                }
            )
    ledger = {
        "schema": LEDGER_SCHEMA,
        "capture_id": contract["capture_id"],
        "contract_id": contract["id"],
        "plan_id": plan["id"],
        "cells": receipts,
    }
    return SemanticExecution(
        capture,
        contract,
        plan,
        frozen_slots,
        expected_cells,
        results,
        ledger,
        canonical_digest(ledger),
    )
