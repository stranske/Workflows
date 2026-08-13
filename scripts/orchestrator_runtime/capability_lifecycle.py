"""Evidence ledger persistence and idempotent capability association."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from scripts.orchestrator_runtime.evidence_schema import (
    CompletionEvidenceError,
    stable_evidence_id,
    validated_payload,
)


class EvidenceLedger:
    """Durable evidence ledger persisted across adapter invocations."""

    def __init__(self, records: list[dict[str, Any]] | None = None) -> None:
        self._records = deepcopy(records or [])

    @classmethod
    def load(cls, path: Path) -> EvidenceLedger:
        if not path.is_file():
            return cls([])
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("evidence ledger must be a list")
        return cls(raw)

    def snapshot(self) -> list[dict[str, Any]]:
        return deepcopy(self._records)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self._records, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def apply_mutation(self, records: list[dict[str, Any]]) -> None:
        self._records = deepcopy(records)


def ingest_completion_evidence(
    payload: Any,
    *,
    capabilities: dict[str, dict[str, Any]],
    ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return an idempotent ledger association without unsafe state transitions."""
    original_capabilities = deepcopy(capabilities)
    original_ledger = deepcopy(ledger)
    try:
        evidence = validated_payload(payload)
        capability = capabilities.get(evidence["capability_id"])
        if not isinstance(capability, dict) or capability.get("lifecycle") not in {
            "candidate",
            "shadow",
        }:
            raise CompletionEvidenceError(
                "spoofed_capability_id: target must be an existing candidate or shadow"
            )
        evidence_id = stable_evidence_id(evidence)
        if any(record.get("evidence_id") == evidence_id for record in ledger):
            return {
                "status": "duplicate",
                "diagnostic_code": "duplicate_evidence",
                "evidence_id": evidence_id,
                "capabilities": original_capabilities,
                "ledger": original_ledger,
            }
        updated_capabilities = deepcopy(capabilities)
        updated_ledger = deepcopy(ledger)
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
