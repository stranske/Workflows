from __future__ import annotations

from scripts.orchestrator_runtime.consumer_sync_report import build_report

CAPABILITY = "capability:reference-sync-hygiene-test-gate"


def _capabilities() -> dict[str, dict[str, object]]:
    return {CAPABILITY: {"lifecycle": "shadow", "counterexamples": []}}


def test_report_classifies_empty_shadow_runtime_as_no_data() -> None:
    report = build_report(_capabilities(), [])

    candidate = report["candidates"][0]
    assert candidate["state"] == "no-data"
    assert candidate["promotion_allowed"] is False
    assert "read-only" in candidate["promotion_blockers"][0]


def test_report_classifies_valid_shadow_evidence_and_keeps_promotion_blocked() -> None:
    report = build_report(
        _capabilities(),
        [
            {
                "capability_id": CAPABILITY,
                "supervision_mode": "shadow",
                "terminal_disposition": "no-change",
            }
        ],
    )

    candidate = report["candidates"][0]
    assert candidate["state"] == "healthy-shadow-evidence"
    assert candidate["promotion_allowed"] is False


def test_report_flags_rejected_or_non_shadow_evidence() -> None:
    rejected = build_report(_capabilities(), [{"capability_id": CAPABILITY, "status": "rejected"}])
    non_shadow = build_report(
        _capabilities(),
        [
            {
                "capability_id": CAPABILITY,
                "supervision_mode": "live",
                "terminal_disposition": "applied",
            }
        ],
    )

    assert rejected["candidates"][0]["state"] == "failed-evidence-ingestion"
    assert non_shadow["candidates"][0]["state"] == "failed-evidence-ingestion"


def test_report_flags_adapter_rejection_without_mutating_the_ledger() -> None:
    report = build_report(_capabilities(), [], rejected_capability_ids=frozenset({CAPABILITY}))

    candidate = report["candidates"][0]
    assert candidate["state"] == "failed-evidence-ingestion"
    assert candidate["evidence_count"] == 0
    assert candidate["policy_classification_owner"] == "Orchestrator/consumer_sync_shadow.py"
