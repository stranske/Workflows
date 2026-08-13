"""Validate and record bounded runner completion evidence.

This is the Workflows-owned adapter boundary for the optional evidence fields
emitted by reusable agent-run workflows.  It deliberately accepts only typed,
schema-shaped evidence and can attach it only to an already-known candidate or
shadow capability.  It never creates, activates, dispatches, or promotes a
capability from runner prose.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.runner_lib import normalize_capability_effect_evidence

SCHEMA = "workflows.runner-completion-evidence/v1"
ALLOWED_KEYS = {
    "schema",
    "capability_id",
    "effect_fingerprint",
    "evidence_artifact_ref",
    "supervision_mode",
    "capability_evidence_status",
    "terminal_disposition",
    "provenance",
    "counterexamples",
}
MAX_COUNTEREXAMPLES = 32
MAX_COUNTEREXAMPLE_LENGTH = 512


class CompletionEvidenceError(ValueError):
    """A rejection that must not mutate the capability state or ledger."""


def _reject(code: str, message: str) -> CompletionEvidenceError:
    return CompletionEvidenceError(f"{code}: {message}")


def _stable_evidence_id(payload: dict[str, Any]) -> str:
    semantic = {
        key: payload[key]
        for key in (
            "capability_id",
            "effect_fingerprint",
            "evidence_artifact_ref",
            "supervision_mode",
            "capability_evidence_status",
            "terminal_disposition",
            "provenance",
            "counterexamples",
        )
    }
    encoded = json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _validated_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise _reject("malformed_evidence", "payload must be an object")
    unknown = set(payload) - ALLOWED_KEYS
    if unknown:
        raise _reject("raw_or_unknown_evidence", "unsupported fields: " + ", ".join(sorted(unknown)))
    missing = ALLOWED_KEYS - set(payload)
    if missing:
        raise _reject("missing_required_evidence", "missing fields: " + ", ".join(sorted(missing)))
    if payload["schema"] != SCHEMA:
        raise _reject("malformed_evidence", "unsupported schema")
    try:
        evidence = normalize_capability_effect_evidence(
            capability_id=payload["capability_id"],
            effect_fingerprint=payload["effect_fingerprint"],
            evidence_artifact_ref=payload["evidence_artifact_ref"],
            supervision_mode=payload["supervision_mode"],
            capability_evidence_status=payload["capability_evidence_status"],
            terminal_disposition=payload["terminal_disposition"],
        )
    except ValueError as exc:
        message = str(exc)
        if "capability_id" in message:
            code = "spoofed_capability_id"
        elif "effect_fingerprint" in message:
            code = "unstable_fingerprint"
        elif "artifact_ref" in message:
            code = "oversized_or_unsafe_ref"
        else:
            code = "malformed_evidence"
        raise _reject(code, message) from exc
    provenance = payload["provenance"]
    if (
        not isinstance(provenance, dict)
        or set(provenance) != {"runner", "run_ref"}
        or not all(isinstance(value, str) and value.strip() for value in provenance.values())
    ):
        raise _reject("missing_provenance", "provenance must contain non-empty runner and run_ref")
    counterexamples = payload["counterexamples"]
    if (
        not isinstance(counterexamples, list)
        or len(counterexamples) > MAX_COUNTEREXAMPLES
        or any(
            not isinstance(item, str)
            or not item.strip()
            or len(item) > MAX_COUNTEREXAMPLE_LENGTH
            for item in counterexamples
        )
    ):
        raise _reject("malformed_counterexamples", "counterexamples must be bounded non-empty strings")
    if evidence.capability_evidence_status != "accepted":
        raise _reject("not_accepted_evidence", "only accepted evidence can be associated")
    return {
        "schema": SCHEMA,
        "capability_id": evidence.capability_id,
        "effect_fingerprint": evidence.effect_fingerprint,
        "evidence_artifact_ref": evidence.evidence_artifact_ref,
        "supervision_mode": evidence.supervision_mode,
        "capability_evidence_status": evidence.capability_evidence_status,
        "terminal_disposition": evidence.terminal_disposition,
        "provenance": {key: value.strip() for key, value in provenance.items()},
        "counterexamples": list(counterexamples),
    }


def ingest_completion_evidence(
    payload: Any,
    *,
    capabilities: dict[str, dict[str, Any]],
    ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return an idempotent ledger association without unsafe state transitions.

    ``capabilities`` and ``ledger`` are copied before mutation.  A rejected
    result returns their original values untouched, making it safe for callers
    to persist only accepted results.
    """
    original_capabilities = copy.deepcopy(capabilities)
    original_ledger = copy.deepcopy(ledger)
    try:
        evidence = _validated_payload(payload)
        capability = capabilities.get(evidence["capability_id"])
        if not isinstance(capability, dict) or capability.get("lifecycle") not in {
            "candidate",
            "shadow",
        }:
            raise _reject("spoofed_capability_id", "target must be an existing candidate or shadow")
        evidence_id = _stable_evidence_id(evidence)
        if any(record.get("evidence_id") == evidence_id for record in ledger):
            return {
                "status": "duplicate",
                "diagnostic_code": "duplicate_evidence",
                "evidence_id": evidence_id,
                "capabilities": original_capabilities,
                "ledger": original_ledger,
            }
        updated_capabilities = copy.deepcopy(capabilities)
        updated_ledger = copy.deepcopy(ledger)
        target = updated_capabilities[evidence["capability_id"]]
        existing_counterexamples = list(target.get("counterexamples") or [])
        for counterexample in evidence["counterexamples"]:
            if counterexample not in existing_counterexamples:
                existing_counterexamples.append(counterexample)
        target["counterexamples"] = existing_counterexamples
        record = {
            "evidence_id": evidence_id,
            "capability_id": evidence["capability_id"],
            "lifecycle": target["lifecycle"],
            "effect_fingerprint": evidence["effect_fingerprint"],
            "evidence_artifact_ref": evidence["evidence_artifact_ref"],
            "supervision_mode": evidence["supervision_mode"],
            "terminal_disposition": evidence["terminal_disposition"],
            "provenance": evidence["provenance"],
            "counterexamples": evidence["counterexamples"],
        }
        updated_ledger.append(record)
        return {
            "status": "accepted",
            "diagnostic_code": "accepted_evidence",
            "evidence_id": evidence_id,
            "capabilities": updated_capabilities,
            "ledger": updated_ledger,
        }
    except CompletionEvidenceError as exc:
        code, _, message = str(exc).partition(": ")
        return {
            "status": "rejected",
            "diagnostic_code": code,
            "message": message,
            "capabilities": original_capabilities,
            "ledger": original_ledger,
        }


def completion_payload_from_shadow_handoff(handoff: Any) -> dict[str, Any]:
    """Translate the existing read-only handoff into typed runner evidence.

    The handoff is already a bounded product of the manifest compiler.  This
    adapter treats its handoff ID as the semantic effect identity and its run
    reference as durable evidence; it never grants write or promotion power.
    """
    if not isinstance(handoff, dict):
        raise _reject("malformed_evidence", "handoff must be an object")
    required = {
        "schema",
        "capability_id",
        "handoff_id",
        "run_ref",
        "supervision_mode",
        "write_authority",
        "promotion_allowed",
    }
    if not required.issubset(handoff):
        raise _reject("malformed_evidence", "handoff lacks required boundary fields")
    if handoff["schema"] != "workflows.consumer-sync-shadow-handoff/v1":
        raise _reject("malformed_evidence", "unsupported handoff schema")
    if handoff["supervision_mode"] != "shadow":
        raise _reject("malformed_evidence", "handoff must remain shadow supervised")
    if handoff["write_authority"] is not False or handoff["promotion_allowed"] is not False:
        raise _reject("unsafe_handoff", "handoff grants write or promotion authority")
    return {
        "schema": SCHEMA,
        "capability_id": handoff["capability_id"],
        "effect_fingerprint": handoff["handoff_id"],
        "evidence_artifact_ref": handoff["run_ref"],
        "supervision_mode": "shadow",
        "capability_evidence_status": "accepted",
        "terminal_disposition": "no-change",
        "provenance": {"runner": "health-69-consumer-sync-shadow-evidence", "run_ref": handoff["run_ref"]},
        "counterexamples": [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
        payload = completion_payload_from_shadow_handoff(handoff)
        result = ingest_completion_evidence(
            payload,
            capabilities={payload["capability_id"]: {"lifecycle": "shadow", "counterexamples": []}},
            ledger=[],
        )
        if result["status"] != "accepted":
            raise _reject(result["diagnostic_code"], result.get("message", "handoff rejected"))
    except (OSError, json.JSONDecodeError, CompletionEvidenceError) as exc:
        parser.error(str(exc))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
