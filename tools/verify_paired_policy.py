"""Restrictive source-owned policy for the fixed MAINT-78 public API screen."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from functools import partial
from time import monotonic

from tools.run_verify_paired import ROOT, load_packet, source_descriptor


@dataclass
class PairedTrial:
    case: str
    policy: dict
    deadline: float
    calls: dict[str, int] = field(
        default_factory=lambda: {"count": 0, "generation": 0, "metadata": 0}
    )
    physical_http_attempts: int = 0

    @classmethod
    def from_environment(cls, capture: dict) -> PairedTrial | None:
        case = os.environ.get("VERIFIER_PAIRED_QUALIFICATION")
        if case is None:
            return None
        descriptor = source_descriptor()
        if case not in descriptor["cases"]:
            raise ValueError("unknown paired qualification fixture")
        if (
            os.environ.get("LANGCHAIN_SLOT_CONFIG") != str(descriptor["slots_path"])
            or os.environ.get("VERIFIER_PAIRED_DESCRIPTOR_SHA256") != descriptor["sha256"]
            or os.environ.get("LANGCHAIN_MODEL_REGISTRY_CONFIG")
            != str(ROOT / "config/model_registry.json")
            or os.environ.get("LANGCHAIN_PROVIDER")
            or os.environ.get("LANGCHAIN_MODEL")
        ):
            raise ValueError("paired trial forbids caller client/registry routing")
        _, policy = load_packet()
        if policy.get("execution_enabled") is not True or policy.get("review_status") != "reviewed":
            raise ValueError("paired trial policy awaits source review")
        original = json.loads((descriptor["root"] / case / "capture.json").read_text())
        if capture != original:
            raise ValueError("paired trial capture differs from reviewed fixture")
        from tools.llm_registry import resolve_slots

        slots = resolve_slots()
        if [(s.provider, s.model) for s in slots] != [
            (row["provider"], row["model"]) for row in policy["models"]
        ]:
            raise ValueError("paired trial requires exact source-owned judge slots")
        try:
            deadline = float(os.environ["VERIFIER_PAIRED_PACKAGE_DEADLINE_MONOTONIC"])
        except (KeyError, ValueError) as exc:
            raise ValueError("original paired package deadline is missing or malformed") from exc
        remaining = deadline - monotonic()
        if not math.isfinite(deadline) or not 0 < remaining <= policy["total_wall_seconds"]:
            raise ValueError("original paired package deadline cannot reset or extend policy")
        return cls(case, policy, deadline)

    def check_matrix(self, prepared: dict, model1: str | None, model2: str | None) -> None:
        if model1 is not None or model2 is not None:
            raise ValueError("paired trial forbids caller model overrides")
        if len(prepared["plan"]["packages"]) != 1:
            raise ValueError("paired trial requires one complete reviewed package")

    def check_prompt(self, prompt: str) -> None:
        expected = load_packet()[0]
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

    def authorize_http_request(self, request: object, *, expected_host: str) -> None:
        """Reserve each actual SDK HTTPX send before transport sees headers."""
        allowed = {
            ("api.openai.com", "POST", "/v1/responses"),
            ("api.openai.com", "POST", "/v1/responses/input_tokens"),
            ("api.anthropic.com", "POST", "/v1/messages"),
            ("api.anthropic.com", "POST", "/v1/messages/count_tokens"),
            ("api.anthropic.com", "GET", "/v1/models/" + self.policy["models"][1]["model"]),
        }
        url = request.url
        if (
            url.scheme != "https"
            or url.port not in (None, 443)
            or url.host != expected_host
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.raw_path != url.path.encode("utf-8")
            or (url.host, request.method, url.path) not in allowed
        ):
            raise ValueError("paired trial HTTP target outside source-owned allowlist")
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            raise ValueError("paired trial wall policy exhausted before HTTP send")
        timeouts = request.extensions.get("timeout")
        if (
            not isinstance(timeouts, dict)
            or set(timeouts) != {"read", "write", "connect", "pool"}
            or any(
                type(value) not in (int, float)
                or not math.isfinite(value)
                or not 0 < value <= self.policy["per_request_timeout_seconds"]
                for value in timeouts.values()
            )
        ):
            raise ValueError("paired trial actual HTTP timeout exceeds policy")
        request.extensions["timeout"] = {
            name: min(value, remaining) for name, value in timeouts.items()
        }
        if self.physical_http_attempts >= self.policy["max_physical_http_attempts"] // 2:
            raise ValueError("paired trial physical HTTP attempt policy exhausted")
        self.physical_http_attempts += 1

    def client(self, client: object) -> object:
        # Client SDKs were already constructed with the finite timeout/retry0.
        # This shallow LC copy retains those same SDK instances and changes only
        # the actual model-visible generation ceiling, checked by native count.
        openai_sdk = getattr(client, "root_client", None)
        sdk = openai_sdk or client._client
        # Restrict the existing SDK-owned HTTPX client in place; no replacement
        # endpoint, transport, credential source or provider is introduced.
        sdk._client.follow_redirects = False
        # Both provider SDKs share this one case-level reservation counter. Run
        # after any existing request hooks, immediately before HTTPX dispatch.
        sdk._client.event_hooks["request"].append(
            partial(
                self.authorize_http_request,
                expected_host="api.openai.com" if openai_sdk is not None else "api.anthropic.com",
            )
        )
        if self.policy.get("preserve_native_output_policy") is True:
            return client
        return client.model_copy(update={"max_tokens": self.policy["max_output_tokens"]})
