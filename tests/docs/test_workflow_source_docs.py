"""Contract tests for source-of-truth workflow docs."""

from __future__ import annotations

from pathlib import Path

import yaml
from tools import langchain_client

README = Path("README.md")
WORKFLOWS_DOC = Path("docs/ci/WORKFLOWS.md")
WORKFLOWS_DIR = Path(".github/workflows")


def _default_compare_models() -> tuple[str, str]:
    slots = {
        slot.provider: slot.model
        for slot in langchain_client._default_slots()  # noqa: SLF001 - docs contract.
    }
    return (
        slots[langchain_client.PROVIDER_OPENAI],
        slots[langchain_client.PROVIDER_ANTHROPIC],
    )


def test_readme_verify_compare_models_match_langchain_defaults() -> None:
    readme = README.read_text(encoding="utf-8")
    openai_model, anthropic_model = _default_compare_models()

    assert "verify:compare" in readme
    assert f"{openai_model} + {anthropic_model}" in readme
    assert "gpt-5.2 + claude-sonnet-4-5" not in readme


def test_workflows_doc_names_gate_autofix_dispatch_path() -> None:
    doc = WORKFLOWS_DOC.read_text(encoding="utf-8")
    gate = (WORKFLOWS_DIR / "pr-00-gate.yml").read_text(encoding="utf-8")

    dispatcher = yaml.safe_load(
        (WORKFLOWS_DIR / "agents-autofix-dispatcher.yml").read_text(encoding="utf-8")
    )
    dispatcher_events = dispatcher.get("on") or dispatcher.get(True) or {}
    dispatch_types = dispatcher_events["repository_dispatch"]["types"]

    assert "no longer triggered automatically after Gate completes" not in doc
    assert "autofix_gate_failure" in gate
    assert "autofix_gate_failure" in dispatch_types
    assert "autofix_gate_failure" in doc
    assert "agents-autofix-dispatcher.yml" in doc
    assert "agents-autofix-loop.yml" in doc
