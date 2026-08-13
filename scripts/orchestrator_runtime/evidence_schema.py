"""Schema and validation for runner completion evidence payloads."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from scripts.runner_lib import normalize_capability_effect_evidence

SCHEMA = "workflows.runner-completion-evidence/v1"
ALLOWED_KEYS = frozenset(
    {
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
)
MAX_COUNTEREXAMPLES = 32
MAX_COUNTEREXAMPLE_LENGTH = 512


class CompletionEvidenceError(ValueError):
    """A rejection that must not mutate capability state or the ledger."""


def reject(code: str, message: str) -> CompletionEvidenceError:
    return CompletionEvidenceError(f"{code}: {message}")


def stable_evidence_id(payload: dict[str, Any]) -> str:
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


def validated_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise reject("malformed_evidence", "payload must be an object")
    unknown = set(payload) - ALLOWED_KEYS
    if unknown:
        raise reject("raw_or_unknown_evidence", "unsupported fields: " + ", ".join(sorted(unknown)))
    missing = ALLOWED_KEYS - set(payload)
    if missing:
        raise reject("missing_required_evidence", "missing fields: " + ", ".join(sorted(missing)))
    if payload["schema"] != SCHEMA:
        raise reject("malformed_evidence", "unsupported schema")
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
        raise reject(code, message) from exc
    provenance = payload["provenance"]
    if (
        not isinstance(provenance, dict)
        or set(provenance) != {"runner", "run_ref"}
        or not all(isinstance(value, str) and value.strip() for value in provenance.values())
    ):
        raise reject("missing_provenance", "provenance must contain non-empty runner and run_ref")
    counterexamples = payload["counterexamples"]
    if (
        not isinstance(counterexamples, list)
        or len(counterexamples) > MAX_COUNTEREXAMPLES
        or any(
            not isinstance(item, str) or not item.strip() or len(item) > MAX_COUNTEREXAMPLE_LENGTH
            for item in counterexamples
        )
    ):
        raise reject(
            "malformed_counterexamples", "counterexamples must be bounded non-empty strings"
        )
    if evidence.capability_evidence_status != "accepted":
        raise reject("not_accepted_evidence", "only accepted evidence can be associated")
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
