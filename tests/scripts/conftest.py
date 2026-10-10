"""Keep response/parser fakes separate from real native transport contract tests."""

import pytest
from scripts.langchain import pr_verifier


@pytest.fixture(autouse=True)
def synthetic_verifier_capacity_contract(monkeypatch):
    native = pr_verifier._native_capacity_contract

    def contract(client):
        # Only explicitly registered unit fakes bypass the native SDK binding.
        # The configured-adapter regressions never set this test-only marker.
        if getattr(client, "_unit_capacity_fake", False) is not True:
            return native(client)
        payload = client._get_request_payload("")
        return {
            "profile": client.profile,
            "provider": "openai" if "input" in payload else "anthropic",
            "model": payload["model"],
            "provenance": "synthetic-unit-test-only",
            "endpoint": "no-network",
        }

    monkeypatch.setattr(pr_verifier, "_native_capacity_contract", contract)
