from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from scripts.build_consumer_sync_shadow_handoff import build_handoff
from scripts.orchestrator_runtime import completion_event_adapter
from scripts.orchestrator_runtime.capabilities import CapabilityRegistry
from scripts.orchestrator_runtime.capability_lifecycle import (
    EvidenceLedger,
    ingest_completion_evidence,
)
from scripts.orchestrator_runtime.completion_event_adapter import process_shadow_handoff
from scripts.orchestrator_runtime.evidence_schema import SCHEMA
from scripts.orchestrator_runtime.runner_effect_bridge import (
    completion_payload_from_shadow_handoff,
    stable_plan_effect_fingerprint,
)
from scripts.sync_manifest_compiler import compile_manifest


def payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema": SCHEMA,
        "capability_id": "capability:reference-sync-hygiene-test-gate",
        "effect_fingerprint": "sha256:" + "a" * 64,
        "evidence_artifact_ref": "github-actions:stranske/Workflows:123:shadow-handoff",
        "supervision_mode": "shadow",
        "capability_evidence_status": "accepted",
        "terminal_disposition": "no-change",
        "provenance": {"runner": "codex", "run_ref": "github-actions:123"},
        "counterexamples": [],
    }
    return {**base, **overrides}


def registry(lifecycle: str = "candidate") -> dict[str, dict[str, object]]:
    return {
        "capability:reference-sync-hygiene-test-gate": {
            "lifecycle": lifecycle,
            "counterexamples": ["existing"],
        }
    }


def real_handoff(run_ref: str) -> dict[str, object]:
    root = Path(__file__).parents[2]
    plan = compile_manifest(root / ".github" / "sync-manifest.yml", repo_root=root).to_plan()
    return build_handoff(plan, run_ref=run_ref)


def test_accepts_known_candidate_and_preserves_lifecycle() -> None:
    result = ingest_completion_evidence(
        payload(counterexamples=["new example"]), capabilities=registry(), ledger=[]
    )

    assert result["status"] == "accepted"
    assert (
        result["capabilities"]["capability:reference-sync-hygiene-test-gate"]["lifecycle"]
        == "candidate"
    )
    assert result["capabilities"]["capability:reference-sync-hygiene-test-gate"][
        "counterexamples"
    ] == [
        "existing",
        "new example",
    ]
    assert len(result["ledger"]) == 1


def test_rejects_unknown_capability_from_authoritative_registry() -> None:
    original = registry()
    result = ingest_completion_evidence(
        payload(capability_id="capability:unknown-capability"),
        capabilities=original,
        ledger=[],
    )

    assert result["diagnostic_code"] == "spoofed_capability_id"
    assert result["capabilities"] == original


def test_replay_is_idempotent_and_has_no_second_mutation() -> None:
    first = ingest_completion_evidence(payload(), capabilities=registry(), ledger=[])
    second = ingest_completion_evidence(
        payload(), capabilities=first["capabilities"], ledger=first["ledger"]
    )

    assert second["status"] == "duplicate"
    assert second["ledger"] == first["ledger"]
    assert second["capabilities"] == first["capabilities"]


def test_plan_fingerprint_is_stable_across_transport_run_refs() -> None:
    first = real_handoff("github-actions:stranske/Workflows:111:1")
    second = real_handoff("github-actions:stranske/Workflows:222:2")

    assert stable_plan_effect_fingerprint(first) == stable_plan_effect_fingerprint(second)
    assert first["handoff_id"] != second["handoff_id"]


def test_shadow_handoff_uses_registry_and_persists_ledger(tmp_path: Path) -> None:
    registry_path = tmp_path / "capabilities.json"
    registry_path.write_text(json.dumps(registry("shadow")), encoding="utf-8")
    state_path = tmp_path / "capabilities-state.json"
    ledger_path = tmp_path / "evidence-ledger.json"
    capability_registry = CapabilityRegistry.load(registry_path)
    capability_registry.save(state_path)
    ledger = EvidenceLedger([])

    handoff = real_handoff("github-actions:stranske/Workflows:123:1")
    first = process_shadow_handoff(handoff, registry=capability_registry, ledger=ledger)
    capability_registry.save(state_path)
    ledger.save(ledger_path)

    reloaded_registry = CapabilityRegistry.load(state_path)
    reloaded_ledger = EvidenceLedger.load(ledger_path)
    second = process_shadow_handoff(handoff, registry=reloaded_registry, ledger=reloaded_ledger)

    assert first["status"] == "accepted"
    assert second["status"] == "duplicate"
    assert reloaded_ledger.snapshot() == ledger.snapshot()


def test_shadow_handoff_rejects_write_or_promotion_authority() -> None:
    handoff = {
        "schema": "workflows.consumer-sync-shadow-handoff/v1",
        "capability_id": "capability:reference-sync-hygiene-test-gate",
        "plan_schema": "workflows.consumer-sync-plan/v1",
        "plan_id": "sha256:" + "b" * 64,
        "manifest_sha256": "sha256:" + "c" * 64,
        "entry_count": 1,
        "removal_count": 0,
        "run_ref": "github-actions:stranske/Workflows:123:1",
        "supervision_mode": "shadow",
        "write_authority": True,
        "promotion_allowed": False,
    }

    with pytest.raises(ValueError, match="unsafe_handoff"):
        completion_payload_from_shadow_handoff(handoff)


def test_cli_preserves_rejection_diagnostic_for_runtime_reporting(tmp_path: Path) -> None:
    handoff = real_handoff("github-actions:stranske/Workflows:124:1")
    handoff["capability_id"] = "capability:unknown"
    handoff_path = tmp_path / "handoff.json"
    output_path = tmp_path / "completion-evidence.json"
    registry_path = tmp_path / "capabilities.json"
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
    registry_path.write_text(json.dumps(registry("shadow")), encoding="utf-8")

    assert (
        completion_event_adapter.main(
            [
                "--handoff",
                str(handoff_path),
                "--output",
                str(output_path),
                "--registry",
                str(registry_path),
                "--state-dir",
                str(tmp_path / "state"),
            ]
        )
        == 1
    )

    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["status"] == "rejected"
    assert result["capability_id"] == "capability:unknown"
    assert (tmp_path / "state" / "capabilities-state.json").is_file()
    assert (tmp_path / "state" / "evidence-ledger.json").is_file()


def test_rejects_unstable_fingerprint_oversized_ref_and_missing_provenance() -> None:
    for invalid, expected in (
        (payload(effect_fingerprint="sha256:broken"), "unstable_fingerprint"),
        (payload(evidence_artifact_ref="a" * 257), "oversized_or_unsafe_ref"),
        (payload(provenance={"runner": "codex"}), "missing_provenance"),
    ):
        original = registry()
        result = ingest_completion_evidence(invalid, capabilities=deepcopy(original), ledger=[])
        assert result["status"] == "rejected"
        assert result["diagnostic_code"] == expected
        assert result["capabilities"] == original
