"""Reviewed, source-owned byte-span rules for semantic verifier packages.

This deliberately does not recognize English.  A registry entry is an audited
mapping for one immutable capture.  It expands a complete capture into named,
hash-bound byte spans and delegates clause/package closure to
``verifier_semantic_acceptance``.  Captures, environment variables, and
provider replies cannot select a rule or assert that a decomposition is safe.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tools.verifier_semantic_acceptance import (
    RULE_SCHEMA,
    build_package_plan,
    canonical_digest,
    compile_contract,
    validate_reassembly,
)

REGISTRY_SCHEMA = "workflows-verifier-semantic-rules/v1"
RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "verifier_semantic_rules.json"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate registry key: {key}")
        result[key] = value
    return result


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hex(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(c in "0123456789abcdef" for c in value)
    )


def load_reviewed_rules() -> tuple[dict[str, Any], ...]:
    """Load the fixed repository registry; there is intentionally no path/env override."""
    try:
        data = json.loads(RULES_PATH.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cannot load source-owned semantic rule registry") from exc
    if not isinstance(data, dict) or data.get("schema") != REGISTRY_SCHEMA:
        raise ValueError("semantic rule registry schema is unknown")
    rules = data.get("rules")
    if not isinstance(rules, list):
        raise ValueError("semantic rule registry rules are malformed")
    if any(not isinstance(rule, dict) for rule in rules):
        raise ValueError("semantic rule registry entry is malformed")
    return tuple(rules)


def _capture_binding(capture: dict[str, Any]) -> dict[str, Any]:
    required = (
        "id",
        "implementation_head",
        "governing_sha256",
        "raw_inputs",
        "gaps",
        "resource_admitted",
    )
    if not isinstance(capture, dict) or any(key not in capture for key in required):
        raise ValueError("capture is incomplete")
    if not isinstance(capture["raw_inputs"], dict):
        raise ValueError("capture raw inputs are malformed")
    return {
        "id": capture["id"],
        "implementation_head": capture["implementation_head"],
        "governing_sha256": capture["governing_sha256"],
        "raw_inputs": dict(capture["raw_inputs"]),
    }


def _entry_binding(entry: dict[str, Any]) -> dict[str, Any]:
    binding = entry.get("binding")
    if not isinstance(binding, dict):
        raise ValueError("reviewed rule has no immutable capture binding")
    if not isinstance(binding.get("raw_inputs"), dict):
        raise ValueError("reviewed rule raw binding is malformed")
    return binding


def resolve_reviewed_rule(
    capture: dict[str, Any], rules: tuple[dict[str, Any], ...] | None = None
) -> dict[str, Any] | None:
    """Return exactly one reviewed entry whose complete capture binding matches."""
    binding = _capture_binding(capture)
    candidates = [
        entry
        for entry in (load_reviewed_rules() if rules is None else rules)
        if _entry_binding(entry) == binding
    ]
    if len(candidates) > 1:
        raise ValueError("multiple reviewed rules bind one capture")
    return candidates[0] if candidates else None


def _validated_spans(
    entry: dict[str, Any], raw_bytes: dict[str, bytes]
) -> tuple[dict[str, Any], dict[str, bytes]]:
    binding = _entry_binding(entry)
    if set(raw_bytes) != set(binding["raw_inputs"]):
        raise ValueError("raw bytes do not exactly match reviewed capture inputs")
    for name, value in raw_bytes.items():
        if not isinstance(value, bytes) or _sha(value) != binding["raw_inputs"][name]:
            raise ValueError("raw bytes do not match the reviewed capture hash")
    raw_spans = entry.get("spans")
    if not isinstance(raw_spans, list) or not raw_spans:
        raise ValueError("reviewed rule has no source spans")
    spans: dict[str, Any] = {}
    pieces: dict[str, bytes] = {}
    coverage: dict[str, list[tuple[int, int]]] = {name: [] for name in raw_bytes}
    package_ids = {item.get("id") for item in entry.get("packages", []) if isinstance(item, dict)}
    for span in raw_spans:
        if not isinstance(span, dict):
            raise ValueError("source span is malformed")
        span_id, source, start, end, owners = (
            span.get(k) for k in ("id", "input", "start", "end", "owners")
        )
        if (
            not isinstance(span_id, str)
            or not span_id
            or span_id in spans
            or source not in raw_bytes
            or type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(raw_bytes[source])
            or not isinstance(owners, list)
            or not owners
            or len(owners) != len(set(owners))
            or not set(owners) <= package_ids
        ):
            raise ValueError("source span identity, ownership, or bounds are malformed")
        piece = raw_bytes[source][start:end]
        if span.get("sha256") != _sha(piece):
            raise ValueError("source span hash is not exact")
        spans[span_id] = {
            "id": span_id,
            "input": source,
            "start": start,
            "end": end,
            "owners": sorted(owners),
            "sha256": _sha(piece),
        }
        pieces[span_id] = piece
        coverage[source].append((start, end))
    for source, intervals in coverage.items():
        cursor = 0
        for start, end in sorted(intervals):
            if start != cursor:
                raise ValueError(
                    "reviewed spans do not account for every capture byte exactly once"
                )
            cursor = end
        if cursor != len(raw_bytes[source]):
            raise ValueError("reviewed spans do not account for every capture byte exactly once")
    _validate_joins(entry, spans)
    return spans, pieces


def _validate_joins(entry: dict[str, Any], spans: dict[str, Any]) -> None:
    joins = entry.get("joins", [])
    if not isinstance(joins, list):
        raise ValueError("reviewed joins are malformed")
    declared: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    for join in joins:
        if not isinstance(join, dict):
            raise ValueError("reviewed join is malformed")
        ids, packages = join.get("span_ids"), join.get("package_ids")
        if (
            not isinstance(ids, list)
            or not ids
            or not isinstance(packages, list)
            or len(packages) < 2
            or len(ids) != len(set(ids))
            or len(packages) != len(set(packages))
            or not set(ids) <= set(spans)
        ):
            raise ValueError("reviewed join identity is malformed")
        if any(set(spans[span_id]["owners"]) != set(packages) for span_id in ids):
            raise ValueError("reviewed join does not declare exact shared ownership")
        declared.add((tuple(sorted(ids)), tuple(sorted(packages))))
    shared = [span for span in spans.values() if len(span["owners"]) > 1]
    for span in shared:
        if ((span["id"],), tuple(span["owners"])) not in declared:
            raise ValueError("shared evidence span lacks an exact declared join")


def prepare_reviewed_execution(
    capture: dict[str, Any],
    raw_bytes: dict[str, bytes],
    *,
    rules: tuple[dict[str, Any], ...] | None = None,
) -> dict[str, Any] | None:
    """Prepare a closure-checked execution capture and exact package prompt members.

    ``None`` means no static reviewed rule binds this capture.  The caller must
    retain an all-input residual obligation; it must never infer a split.
    """
    entry = resolve_reviewed_rule(capture, rules)
    if entry is None:
        return None
    spans, pieces = _validated_spans(entry, raw_bytes)
    rule = entry.get("rule")
    if not isinstance(rule, dict) or rule.get("schema") != RULE_SCHEMA:
        raise ValueError("reviewed rule body is malformed")
    # The capture identity stays original; only raw dependency identities expand
    # to immutable spans after original full-input hashes have been checked.
    execution_capture = dict(capture)
    execution_capture["raw_inputs"] = {
        span_id: data["sha256"] for span_id, data in sorted(spans.items())
    }
    contract = compile_contract(
        execution_capture, rule, trusted_rule_digests=(canonical_digest(rule),)
    )
    specs = entry.get("packages")
    if not isinstance(specs, list) or len(specs) > 8:
        raise ValueError("reviewed package specs are malformed")
    plan = build_package_plan(contract, specs)
    _validate_global_clause_copies(entry, contract, plan, spans)
    validate_reassembly(execution_capture, contract, plan)
    prompts = build_package_prompts(execution_capture, contract, plan, spans, pieces)
    return {
        "capture": execution_capture,
        "contract": contract,
        "plan": plan,
        "prompts": prompts,
        "rule": entry,
    }


def _validate_global_clause_copies(
    entry: dict[str, Any], contract: dict[str, Any], plan: dict[str, Any], spans: dict[str, Any]
) -> None:
    """Require reviewed global clauses to accompany every package sharing evidence."""
    declared = entry.get("global_clause_ids_by_package")
    packages = {item["id"]: set(item["clause_ids"]) for item in plan["packages"]}
    if not isinstance(declared, dict) or set(declared) != set(packages):
        raise ValueError("reviewed global clause copies are not declared for every package")
    clauses = {item["id"]: item for item in contract["clauses"]}
    shared_ids = {span_id for span_id, span in spans.items() if len(span["owners"]) > 1}
    for package_id, clause_ids in declared.items():
        if (
            not isinstance(clause_ids, list)
            or not clause_ids
            or len(clause_ids) != len(set(clause_ids))
        ):
            raise ValueError("reviewed global clause copy is malformed")
        if not set(clause_ids) <= packages[package_id]:
            raise ValueError("reviewed global clause is absent from its package")
        dependencies = set().union(
            *(set(clauses[clause_id]["raw_dependencies"]) for clause_id in clause_ids)
        )
        owned_shared = {span_id for span_id in shared_ids if package_id in spans[span_id]["owners"]}
        if not owned_shared <= dependencies:
            raise ValueError("reviewed global clause does not copy all shared governing evidence")


def prepare_residual_all_input(
    capture: dict[str, Any], raw_bytes: dict[str, bytes]
) -> dict[str, Any]:
    """Make the only safe fallback: one residual obligation over every raw byte.

    It is intentionally one package, so an over-limit complete capture blocks
    rather than being narrowed by an unreviewed heuristic.
    """
    binding = _capture_binding(capture)
    if set(raw_bytes) != set(binding["raw_inputs"]) or any(
        not isinstance(value, bytes) or _sha(value) != binding["raw_inputs"][name]
        for name, value in raw_bytes.items()
    ):
        raise ValueError("residual fallback raw bytes do not match capture identity")
    rule = {
        "schema": RULE_SCHEMA,
        "capture_id": capture["id"],
        "governing_sha256": capture["governing_sha256"],
        "clauses": [
            {
                "id": "residual-all-input",
                "predicate": "provenance",
                "raw_dependencies": sorted(raw_bytes),
                "requires": [],
                "joint_groups": ["residual-all-input"],
                "residual": True,
            }
        ],
    }
    spans = {
        name: {
            "id": name,
            "input": name,
            "start": 0,
            "end": len(value),
            "owners": ["residual"],
            "sha256": _sha(value),
        }
        for name, value in raw_bytes.items()
    }
    contract = compile_contract(capture, rule, trusted_rule_digests=(canonical_digest(rule),))
    plan = build_package_plan(
        contract,
        [{"id": "residual", "clause_ids": ["residual-all-input"], "raw_inputs": sorted(raw_bytes)}],
    )
    prompts = build_package_prompts(capture, contract, plan, spans, dict(raw_bytes))
    return {
        "capture": dict(capture),
        "contract": contract,
        "plan": plan,
        "prompts": prompts,
        "rule": None,
    }


def build_package_prompts(
    capture: dict[str, Any],
    contract: dict[str, Any],
    plan: dict[str, Any],
    spans: dict[str, Any],
    pieces: dict[str, bytes],
) -> dict[str, dict[str, Any]]:
    """Return framed prompts whose members retain exact reviewed source bytes."""
    validate_reassembly(capture, contract, plan)
    prompts: dict[str, dict[str, Any]] = {}
    for package in plan["packages"]:
        required = package["raw_inputs"]
        if set(required) != {
            span_id for span_id, span in spans.items() if package["id"] in span["owners"]
        }:
            raise ValueError("package ownership differs from declared dependency closure")
        members = []
        for span_id in required:
            span = spans.get(span_id)
            piece = pieces.get(span_id)
            if span is None or piece is None or _sha(piece) != span["sha256"]:
                raise ValueError("package prompt cannot reassemble exact reviewed span bytes")
            members.append({**span, "bytes": piece})
        members.sort(key=lambda item: (item["input"], item["start"], item["id"]))
        # Framing is deterministic metadata; captured bytes themselves are never
        # decoded, escaped, clipped, or substituted.
        framed = b"".join(
            b"\n-- semantic-span " + item["id"].encode("ascii") + b" --\n" + item["bytes"]
            for item in members
        )
        prompts[package["id"]] = {
            "package_id": package["id"],
            "members": members,
            "bytes": framed,
            "sha256": _sha(framed),
        }
    return prompts


def preflight_package_prompts(
    prompts: dict[str, dict[str, Any]], preflight: Callable[[str, bytes], Any]
) -> dict[str, Any]:
    """Call preflight for every package before a caller performs any generation."""
    outcomes: dict[str, Any] = {}
    for package_id in sorted(prompts):
        prompt = prompts[package_id]
        if _sha(prompt["bytes"]) != prompt["sha256"]:
            raise ValueError("package prompt changed after exact-byte construction")
        outcomes[package_id] = preflight(package_id, prompt["bytes"])
    return outcomes


def preflight_then_invoke(
    prompts: dict[str, dict[str, Any]],
    preflight: Callable[[str, bytes], bool],
    invoke: Callable[[str, bytes], Any],
) -> dict[str, Any]:
    """Invoke no package unless every frozen package first passed preflight."""
    outcomes = preflight_package_prompts(prompts, preflight)
    if any(outcome is not True for outcome in outcomes.values()):
        raise ValueError("semantic package preflight did not admit every package")
    return {
        package_id: invoke(package_id, prompts[package_id]["bytes"])
        for package_id in sorted(prompts)
    }
