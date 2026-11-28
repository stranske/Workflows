"""Native capacity capabilities for response/coverage unit-test clients (no network)."""

from types import SimpleNamespace
from unittest import mock

import pytest
from scripts.langchain import pr_verifier


def with_capacity(client):
    client._unit_capacity_fake = True
    client.profile = {"max_input_tokens": 1_000_000, "max_output_tokens": 4096}
    client.max_tokens = 4096
    client._get_request_payload = lambda prompt: {
        "model": "unit-test-model",
        "input": [{"role": "user", "content": prompt}],
        "max_output_tokens": 4096,
    }
    client.root_client = SimpleNamespace(
        responses=SimpleNamespace(
            input_tokens=SimpleNamespace(
                count=mock.Mock(return_value=SimpleNamespace(input_tokens=1000))
            )
        )
    )
    return client


def complete_capture_context():
    """Small builder-shaped capture with every required source retained."""
    import json

    diff = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n"
    inventory = {
        "schema": "verifier-context-source-coverage/v1",
        "stage": "generated-context",
        "changed_code_sources": [
            {
                "source": "a.py",
                "status": "included",
                "included_chars": len(diff),
                "total_chars": len(diff),
            }
        ],
        "acceptance_sources": [
            {"source": "pr:1", "status": "included", "included_chars": 12, "total_chars": 12}
        ],
        "acceptance_evidence_sources": [],
        "acceptance_source_discovery": {"required": False, "status": "included"},
        "full_diff_artifact": {
            "source": "verifier-pr-diff.patch",
            "status": "included",
            "chars": len(diff),
        },
    }
    context = (
        "# Verifier context\n\n## Context source coverage\n\n```json\n"
        + json.dumps(inventory)
        + "\n```\n\n## CI Information\nNo failures.\n\n"
        "## Plan sources (scope, tasks, acceptance)\n"
        "#### Acceptance criteria\n- Implement the code change.\n\n"
        "## PR Diff Summary\n- Files changed: 1\n\n### File changes\n- a.py (+1/-1)\n\n"
        "## PR Diff (full)\n\n```diff\n" + diff + "```\n"
    )
    return context


@pytest.fixture
def synthetic_verifier_capacity_contract(monkeypatch):
    native = pr_verifier._native_capacity_contract

    def contract(client, **kwargs):
        # Only explicitly registered unit fakes bypass the native SDK binding.
        # The configured-adapter regressions never set this test-only marker.
        # Keyword arguments (for example a paired `trial`) pass through unchanged.
        if getattr(client, "_unit_capacity_fake", False) is not True:
            return native(client, **kwargs)
        payload = client._get_request_payload("")
        return {
            "profile": client.profile,
            "provider": "openai" if "input" in payload else "anthropic",
            "model": payload["model"],
            "provenance": "synthetic-unit-test-only",
            "endpoint": "no-network",
        }

    monkeypatch.setattr(pr_verifier, "_native_capacity_contract", contract)
