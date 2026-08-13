"""Translate bounded runner handoffs into typed completion evidence payloads."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from scripts.orchestrator_runtime.evidence_schema import SCHEMA, reject

HANDOFF_SCHEMA = "workflows.consumer-sync-shadow-handoff/v1"


def _stable_hash(namespace: str, value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(namespace.encode() + b"\0" + encoded).hexdigest()


def stable_plan_effect_fingerprint(handoff: dict[str, Any]) -> str:
    """Derive semantic plan identity without transport-only run references."""
    semantic = {
        "capability_id": handoff["capability_id"],
        "plan_schema": handoff["plan_schema"],
        "plan_id": handoff["plan_id"],
        "manifest_sha256": handoff["manifest_sha256"],
        "entry_count": handoff["entry_count"],
        "removal_count": handoff["removal_count"],
    }
    return _stable_hash("consumer-sync-plan-effect", semantic)


def completion_payload_from_shadow_handoff(handoff: Any) -> dict[str, Any]:
    """Translate a bounded shadow handoff into typed runner evidence."""
    if not isinstance(handoff, dict):
        raise reject("malformed_evidence", "handoff must be an object")
    required = {
        "schema",
        "capability_id",
        "plan_schema",
        "plan_id",
        "manifest_sha256",
        "entry_count",
        "removal_count",
        "run_ref",
        "supervision_mode",
        "write_authority",
        "promotion_allowed",
    }
    if not required.issubset(handoff):
        raise reject("malformed_evidence", "handoff lacks required boundary fields")
    if handoff["schema"] != HANDOFF_SCHEMA:
        raise reject("malformed_evidence", "unsupported handoff schema")
    if handoff["supervision_mode"] != "shadow":
        raise reject("malformed_evidence", "handoff must remain shadow supervised")
    if handoff["write_authority"] is not False or handoff["promotion_allowed"] is not False:
        raise reject("unsafe_handoff", "handoff grants write or promotion authority")
    return {
        "schema": SCHEMA,
        "capability_id": handoff["capability_id"],
        "effect_fingerprint": stable_plan_effect_fingerprint(handoff),
        "evidence_artifact_ref": handoff["run_ref"],
        "supervision_mode": "shadow",
        "capability_evidence_status": "accepted",
        "terminal_disposition": "no-change",
        "provenance": {
            "runner": "health-69-consumer-sync-shadow-evidence",
            "run_ref": handoff["run_ref"],
        },
        "counterexamples": [],
    }
