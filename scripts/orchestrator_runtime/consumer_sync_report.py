"""Report the bounded consumer-sync shadow runtime state.

The report is deliberately read-only.  It is an operational observation of the
evidence ledger, not a promotion mechanism: consumer-sync stays in shadow mode
until an owning policy explicitly enables a later promotion path.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.orchestrator_runtime.capabilities import CapabilityRegistry
from scripts.orchestrator_runtime.capability_lifecycle import EvidenceLedger

SHADOW_STATES = frozenset({"no-data", "healthy-shadow-evidence", "failed-evidence-ingestion"})
PROMOTION_BLOCKERS = (
    "consumer-sync effects are read-only",
    "consumer-sync promotion is disabled",
    "shadow evidence is not write-authority evidence",
)


def _state_for(
    capability_id: str, ledger: list[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    records = [record for record in ledger if record.get("capability_id") == capability_id]
    if not records:
        return "no-data", records
    if any(record.get("status") == "rejected" for record in records):
        return "failed-evidence-ingestion", records
    if all(
        record.get("supervision_mode") == "shadow"
        and record.get("terminal_disposition") == "no-change"
        for record in records
    ):
        return "healthy-shadow-evidence", records
    return "failed-evidence-ingestion", records


def build_report(
    capabilities: dict[str, dict[str, Any]], ledger: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return one explicit health state per registered capability."""
    candidates = []
    for capability_id in sorted(capabilities):
        state, records = _state_for(capability_id, ledger)
        candidates.append(
            {
                "capability_id": capability_id,
                "state": state,
                "evidence_count": len(records),
                "counterexample_count": len(capabilities[capability_id].get("counterexamples", [])),
                "promotion_allowed": False,
                "promotion_blockers": list(PROMOTION_BLOCKERS),
            }
        )
    assert all(candidate["state"] in SHADOW_STATES for candidate in candidates)
    return {"schema": "workflows.consumer-sync-runtime-report/v1", "candidates": candidates}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = build_report(
        CapabilityRegistry.load(args.registry).snapshot(),
        EvidenceLedger.load(args.ledger).snapshot(),
    )
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
