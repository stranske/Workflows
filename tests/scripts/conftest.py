"""Keep response/parser fakes separate from real native transport contract tests."""

import pytest
from scripts.langchain import pr_verifier


@pytest.fixture(autouse=True)
def isolate_deliberate_break_worker_subprocesses(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    if request.node.path.name == "test_check_deliberate_break.py" and hasattr(
        request.config, "workerinput"
    ):
        # These child pytest runs use synthetic conftests. Leave the archived
        # serial comparison's plugin environment intact.
        monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")


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
