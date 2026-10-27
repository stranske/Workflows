"""Restrictive source-owned policy for the fixed MAINT-78 public API screen."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from time import monotonic

from tools.run_verify_paired import CASES, PACKET, ROOT, load_packet


@dataclass
class PairedTrial:
    case: str
    policy: dict
    deadline: float
    calls: dict[str, int] = field(
        default_factory=lambda: {"count": 0, "generation": 0, "metadata": 0}
    )

    @classmethod
    def from_environment(cls, capture: dict) -> PairedTrial | None:
        case = os.environ.get("VERIFIER_PAIRED_QUALIFICATION")
        if case is None:
            return None
        if case not in CASES:
            raise ValueError("unknown paired qualification fixture")
        if (
            os.environ.get("LANGCHAIN_SLOT_CONFIG") != str(PACKET / "slots.json")
            or os.environ.get("LANGCHAIN_MODEL_REGISTRY_CONFIG")
            != str(ROOT / "config/model_registry.json")
            or os.environ.get("LANGCHAIN_PROVIDER")
            or os.environ.get("LANGCHAIN_MODEL")
        ):
            raise ValueError("paired trial forbids caller client/registry routing")
        _, policy = load_packet()
        if policy.get("execution_enabled") is not True or policy.get("review_status") != "reviewed":
            raise ValueError("paired trial policy awaits source review")
        original = json.loads((PACKET / case / "capture.json").read_text())
        if capture != original:
            raise ValueError("paired trial capture differs from reviewed fixture")
        from tools.llm_registry import resolve_slots

        slots = resolve_slots()
        if [(s.provider, s.model) for s in slots] != [
            (row["provider"], row["model"]) for row in policy["models"]
        ]:
            raise ValueError("paired trial requires exact source-owned judge slots")
        return cls(case, policy, monotonic() + policy["total_wall_seconds"])

    def check_matrix(self, prepared: dict, model1: str | None, model2: str | None) -> None:
        if model1 is not None or model2 is not None:
            raise ValueError("paired trial forbids caller model overrides")
        if len(prepared["plan"]["packages"]) != 1:
            raise ValueError("paired trial requires one complete reviewed package")

    def check_prompt(self, prompt: str) -> None:
        expected = json.loads((PACKET / "PROPOSAL.json").read_text())
        case = next(row for row in expected["cases"] if row["case"] == self.case)
        if hashlib.sha256(prompt.encode()).hexdigest() != case["prompt_sha256"]:
            raise ValueError("paired trial full prompt differs from reviewed bytes")

    def consume(self, kind: str) -> None:
        if monotonic() >= self.deadline:
            raise ValueError("paired trial wall policy exhausted")
        limits = {"count": 4, "generation": 2, "metadata": 3}
        if kind not in limits or self.calls[kind] >= limits[kind]:
            raise ValueError(f"paired trial {kind} request policy exhausted")
        self.calls[kind] += 1

    def check_sdk(self, sdk: object) -> None:
        if sdk.max_retries != 0:
            raise ValueError("paired trial forbids native SDK retries")
        if sdk._client.follow_redirects is not False:
            raise ValueError("paired trial forbids native HTTP redirects")
        timeout = sdk.timeout
        values = (
            [timeout]
            if isinstance(timeout, (int, float))
            else [getattr(timeout, name, None) for name in ("read", "write", "connect", "pool")]
        )
        if any(
            type(value) not in (int, float)
            or not 0 < value <= self.policy["per_request_timeout_seconds"]
            for value in values
        ):
            raise ValueError("paired trial native SDK timeout exceeds policy")

    def client(self, client: object) -> object:
        # Client SDKs were already constructed with the finite timeout/retry0.
        # This shallow LC copy retains those same SDK instances and changes only
        # the actual model-visible generation ceiling, checked by native count.
        sdk = getattr(client, "root_client", None) or client._client
        # Restrict the existing SDK-owned HTTPX client in place; no replacement
        # endpoint, transport, credential source or provider is introduced.
        sdk._client.follow_redirects = False
        return client.model_copy(update={"max_tokens": self.policy["max_output_tokens"]})
