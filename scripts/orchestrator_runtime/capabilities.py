"""Authoritative capability registry for orchestrator evidence ingestion."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class CapabilityRegistry:
    """Load and persist the authoritative candidate/shadow capability registry."""

    def __init__(self, capabilities: dict[str, dict[str, Any]]) -> None:
        self._capabilities = deepcopy(capabilities)

    @classmethod
    def load(cls, path: Path) -> CapabilityRegistry:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("capability registry must be an object")
        capabilities: dict[str, dict[str, Any]] = {}
        for capability_id, record in raw.items():
            if not isinstance(capability_id, str) or not isinstance(record, dict):
                raise ValueError("capability registry entries must be capability-id objects")
            lifecycle = record.get("lifecycle")
            if lifecycle not in {"candidate", "shadow"}:
                raise ValueError(f"unsupported lifecycle for {capability_id}")
            counterexamples = record.get("counterexamples", [])
            if not isinstance(counterexamples, list):
                raise ValueError(f"counterexamples for {capability_id} must be a list")
            capabilities[capability_id] = {
                "lifecycle": lifecycle,
                "counterexamples": list(counterexamples),
            }
        return cls(capabilities)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return deepcopy(self._capabilities)

    def get(self, capability_id: str) -> dict[str, Any] | None:
        record = self._capabilities.get(capability_id)
        return deepcopy(record) if isinstance(record, dict) else None

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self._capabilities, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def apply_mutation(self, capabilities: dict[str, dict[str, Any]]) -> None:
        self._capabilities = deepcopy(capabilities)
