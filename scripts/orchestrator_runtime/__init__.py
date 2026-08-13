"""Versioned orchestrator runtime rail for completion-event evidence handling."""

from scripts.orchestrator_runtime.capability_lifecycle import ingest_completion_evidence
from scripts.orchestrator_runtime.completion_event_adapter import main as completion_event_main
from scripts.orchestrator_runtime.runner_effect_bridge import completion_payload_from_shadow_handoff

__all__ = [
    "completion_event_main",
    "completion_payload_from_shadow_handoff",
    "ingest_completion_evidence",
]
