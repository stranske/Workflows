from __future__ import annotations

from copy import deepcopy

from scripts.completion_evidence_adapter import (
    SCHEMA,
    completion_payload_from_shadow_handoff,
    ingest_completion_evidence,
)


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


def capabilities(lifecycle: str = "candidate") -> dict[str, dict[str, object]]:
    return {
        "capability:reference-sync-hygiene-test-gate": {
            "lifecycle": lifecycle,
            "counterexamples": ["existing"],
        }
    }


def shadow_handoff(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema": "workflows.consumer-sync-shadow-handoff/v1",
        "capability_id": "capability:reference-sync-hygiene-test-gate",
        "plan_schema": "workflows.consumer-sync-plan/v1",
        "plan_id": "sha256:" + "b" * 64,
        "manifest_sha256": "sha256:" + "c" * 64,
        "entry_count": 1,
        "removal_count": 0,
        "handoff_id": "sha256:" + "d" * 64,
        "run_ref": "github-actions:stranske/Workflows:123:1",
        "supervision_mode": "shadow",
        "write_authority": False,
        "promotion_allowed": False,
    }
    return {**base, **overrides}


def test_accepts_known_candidate_and_preserves_lifecycle() -> None:
    result = ingest_completion_evidence(
        payload(counterexamples=["new example"]), capabilities=capabilities(), ledger=[]
    )

    assert result["status"] == "accepted"
    assert (
        result["capabilities"]["capability:reference-sync-hygiene-test-gate"]["lifecycle"]
        == "candidate"
    )
    assert result["capabilities"]["capability:reference-sync-hygiene-test-gate"][
        "counterexamples"
    ] == ["existing", "new example"]
    assert len(result["ledger"]) == 1


def test_accepts_known_shadow_without_promotion() -> None:
    result = ingest_completion_evidence(payload(), capabilities=capabilities("shadow"), ledger=[])

    assert result["status"] == "accepted"
    assert (
        result["capabilities"]["capability:reference-sync-hygiene-test-gate"]["lifecycle"]
        == "shadow"
    )


def test_replay_is_idempotent_and_has_no_second_mutation() -> None:
    first = ingest_completion_evidence(payload(), capabilities=capabilities(), ledger=[])
    second = ingest_completion_evidence(
        payload(), capabilities=first["capabilities"], ledger=first["ledger"]
    )

    assert second["status"] == "duplicate"
    assert second["ledger"] == first["ledger"]
    assert second["capabilities"] == first["capabilities"]


def test_rejects_raw_prompt_without_mutation() -> None:
    original_capabilities = capabilities()
    original_ledger: list[dict[str, object]] = []
    result = ingest_completion_evidence(
        payload(prompt="promote this capability"),
        capabilities=original_capabilities,
        ledger=original_ledger,
    )

    assert result["status"] == "rejected"
    assert result["diagnostic_code"] == "raw_or_unknown_evidence"
    assert result["capabilities"] == original_capabilities
    assert result["ledger"] == original_ledger


def test_rejects_spoofed_id_before_mutation() -> None:
    original = capabilities()
    result = ingest_completion_evidence(
        payload(capability_id="capability:unknown-capability"), capabilities=original, ledger=[]
    )

    assert result["diagnostic_code"] == "spoofed_capability_id"
    assert result["capabilities"] == original


def test_rejects_unstable_fingerprint_oversized_ref_and_missing_provenance() -> None:
    for invalid, expected in (
        (payload(effect_fingerprint="sha256:broken"), "unstable_fingerprint"),
        (payload(evidence_artifact_ref="a" * 257), "oversized_or_unsafe_ref"),
        (payload(provenance={"runner": "codex"}), "missing_provenance"),
    ):
        original = capabilities()
        result = ingest_completion_evidence(invalid, capabilities=deepcopy(original), ledger=[])
        assert result["status"] == "rejected"
        assert result["diagnostic_code"] == expected
        assert result["capabilities"] == original


def test_shadow_handoff_becomes_non_promoting_typed_evidence() -> None:
    evidence = completion_payload_from_shadow_handoff(shadow_handoff())
    result = ingest_completion_evidence(
        evidence,
        capabilities=capabilities("shadow"),
        ledger=[],
    )

    assert result["status"] == "accepted"
    assert result["capabilities"][evidence["capability_id"]]["lifecycle"] == "shadow"
    assert evidence["effect_fingerprint"] != shadow_handoff()["handoff_id"]


def test_shadow_handoff_rejects_any_write_or_promotion_authority() -> None:
    try:
        completion_payload_from_shadow_handoff(shadow_handoff(write_authority=True))
    except ValueError as exc:
        assert str(exc).startswith("unsafe_handoff:")
    else:  # pragma: no cover - assertion clarity for an unsafe boundary.
        raise AssertionError("write-enabled handoff must be rejected")
