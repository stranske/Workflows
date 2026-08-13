"""CLI entry point for Health 69 and orchestrator completion-event ingestion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.orchestrator_runtime.capabilities import CapabilityRegistry
from scripts.orchestrator_runtime.capability_lifecycle import (
    EvidenceLedger,
    ingest_completion_evidence,
)
from scripts.orchestrator_runtime.evidence_schema import CompletionEvidenceError
from scripts.orchestrator_runtime.runner_effect_bridge import completion_payload_from_shadow_handoff

DEFAULT_REGISTRY = Path("config/orchestrator_runtime/capabilities.json")
RESULT_SCHEMA = "workflows.runner-completion-evidence-result/v1"


def _load_runtime_capabilities(registry_path: Path, state_path: Path) -> CapabilityRegistry:
    if state_path.is_file():
        return CapabilityRegistry.load(state_path)
    registry = CapabilityRegistry.load(registry_path)
    registry.save(state_path)
    return registry


def process_shadow_handoff(
    handoff: dict[str, object],
    *,
    registry: CapabilityRegistry,
    ledger: EvidenceLedger,
) -> dict[str, object]:
    payload = completion_payload_from_shadow_handoff(handoff)
    result = ingest_completion_evidence(
        payload,
        capabilities=registry.snapshot(),
        ledger=ledger.snapshot(),
    )
    if result["status"] == "accepted":
        registry.apply_mutation(result["capabilities"])
        ledger.apply_mutation(result["ledger"])
    return result


def _rejected_result(raw_handoff: object, exc: Exception) -> dict[str, object]:
    """Serialize a rejection without granting the rejected payload any authority."""
    code, separator, message = str(exc).partition(": ")
    result: dict[str, object] = {
        "schema": RESULT_SCHEMA,
        "status": "rejected",
        "diagnostic_code": code if separator else "malformed_evidence",
        "message": message if separator else str(exc),
    }
    if isinstance(raw_handoff, dict) and isinstance(raw_handoff.get("capability_id"), str):
        # This is diagnostic correlation only.  The rejected value is never used
        # to mutate the registry or ledger.
        result["capability_id"] = raw_handoff["capability_id"]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="Authoritative capability registry JSON path",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        help="Mutable runtime state directory for capabilities and ledger persistence",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        help="Persistent evidence ledger JSON path (defaults to <state-dir>/evidence-ledger.json)",
    )
    args = parser.parse_args(argv)
    state_dir = args.state_dir or args.output.parent
    state_dir.mkdir(parents=True, exist_ok=True)
    capabilities_state_path = state_dir / "capabilities-state.json"
    ledger_path = args.ledger or (state_dir / "evidence-ledger.json")
    handoff: object | None = None
    try:
        handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
        registry = _load_runtime_capabilities(args.registry, capabilities_state_path)
        # Keep a reportable read-only snapshot even when the incoming evidence is
        # rejected before any registry mutation can occur.
        registry.save(capabilities_state_path)
        ledger = EvidenceLedger.load(ledger_path)
        result = process_shadow_handoff(handoff, registry=registry, ledger=ledger)
        if result["status"] == "rejected" and isinstance(handoff, dict):
            capability_id = handoff.get("capability_id")
            if isinstance(capability_id, str):
                result["capability_id"] = capability_id
        registry.apply_mutation(result["capabilities"])
        ledger.apply_mutation(result["ledger"])
        registry.save(capabilities_state_path)
        ledger.save(ledger_path)
    except (OSError, json.JSONDecodeError, CompletionEvidenceError, ValueError) as exc:
        result = _rejected_result(handoff, exc)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("status") in {"accepted", "duplicate"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
