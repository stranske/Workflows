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
from scripts.orchestrator_runtime.evidence_schema import CompletionEvidenceError, reject
from scripts.orchestrator_runtime.runner_effect_bridge import completion_payload_from_shadow_handoff

DEFAULT_REGISTRY = Path("config/orchestrator_runtime/capabilities.json")


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
    try:
        handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
        registry = _load_runtime_capabilities(args.registry, capabilities_state_path)
        ledger = EvidenceLedger.load(ledger_path)
        result = process_shadow_handoff(handoff, registry=registry, ledger=ledger)
        if result["status"] != "accepted":
            raise reject(result["diagnostic_code"], result.get("message", "handoff rejected"))
        registry.save(capabilities_state_path)
        ledger.save(ledger_path)
    except (OSError, json.JSONDecodeError, CompletionEvidenceError, ValueError) as exc:
        parser.error(str(exc))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
