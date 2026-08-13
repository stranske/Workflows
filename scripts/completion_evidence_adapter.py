"""Backward-compatible re-exports for the versioned orchestrator runtime rail."""

from __future__ import annotations

from scripts.orchestrator_runtime.capability_lifecycle import ingest_completion_evidence
from scripts.orchestrator_runtime.completion_event_adapter import main
from scripts.orchestrator_runtime.evidence_schema import SCHEMA
from scripts.orchestrator_runtime.runner_effect_bridge import completion_payload_from_shadow_handoff

CompletionEvidenceError = __import__(
    "scripts.orchestrator_runtime.evidence_schema", fromlist=["CompletionEvidenceError"]
).CompletionEvidenceError

__all__ = [
    "CompletionEvidenceError",
    "SCHEMA",
    "completion_payload_from_shadow_handoff",
    "ingest_completion_evidence",
    "main",
]
