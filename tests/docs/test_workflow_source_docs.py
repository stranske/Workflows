"""Contract tests for source-of-truth workflow docs."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from tools import langchain_client

README = Path("README.md")
WORKFLOWS_DOC = Path("docs/ci/WORKFLOWS.md")
WORKFLOWS_DIR = Path(".github/workflows")
AGENT_REGISTRY = Path(".github/agents/registry.yml")
MULTI_AGENT_ROUTING_DOC = Path("docs/keepalive/MULTI_AGENT_ROUTING.md")
ACTIVE_VERIFIER_DOCS = (
    Path("README.md"),
    Path("docs/WORKFLOW_GUIDE.md"),
    Path("docs/ci/WORKFLOWS.md"),
    Path("docs/LABELS.md"),
)


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
    assert "shorthand for files under `.github/workflows/`" in doc
    assert 'gate --> autofix["Reusable 18 Autofix' not in doc
    assert not re.search(
        r'gate\s*-->\s*autofix\["Reusable 18 Autofix',
        doc,
    )
    assert 'gate --> autofixDispatch["Autofix Dispatch' in doc
    assert 'autofixDispatch --> autofixLoop["Agents Autofix Loop' in doc


def test_agent_routing_doc_covers_enabled_registry_agents() -> None:
    registry = yaml.safe_load(AGENT_REGISTRY.read_text(encoding="utf-8"))
    routing_doc = MULTI_AGENT_ROUTING_DOC.read_text(encoding="utf-8")

    active_runners = {
        agent: config["runner_workflow"]
        for agent, config in registry["agents"].items()
        if config.get("runner_workflow") and config.get("enabled", True) is not False
    }

    assert set(active_runners) == {"codex", "claude", "cursor", "gemini"}

    missing = [
        f"{agent} ({Path(workflow).name})"
        for agent, workflow in active_runners.items()
        if f"agent:{agent}" not in routing_doc or Path(workflow).name not in routing_doc
    ]

    assert (
        not missing
    ), "docs/keepalive/MULTI_AGENT_ROUTING.md is missing active registry agents: " + ", ".join(
        missing
    )


def test_active_docs_do_not_claim_automatic_verifier_followup() -> None:
    stale_followup_claim = re.compile(
        r"(?i)("
        r"(?:on|when)\s+(?:concerns|fail|failure|verdict is fail)[^.|\n]*"
        r"(?:creates?|opens?|is opened)[^.|\n]*follow-up issue"
        r"|"
        r"follow-up issue is opened[^.|\n]*(?:fail|failure|concerns)"
        r"|"
        r"creates?[^.|\n]*follow-up issues?[^.|\n]*(?:when|on)[^.|\n]*(?:concerns|fail|failure)"
        r"|"
        r"creates?[^.|\n]*follow-up issues?[^.|\n]*gaps"
        r"|"
        r"failures open issues"
        r")"
    )
    manual_label_caveat = re.compile(
        r"(?i)verify:create-(?:issue|new-pr)|label-triggered|manual|maintainers? or automation"
    )

    failures: list[str] = []
    for path in ACTIVE_VERIFIER_DOCS:
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if not stale_followup_claim.search(line):
                continue
            context = "\n".join(lines[max(0, index - 2) : index + 3])
            if not manual_label_caveat.search(context):
                failures.append(f"{path}:{index + 1}: {line.strip()}")

    assert not failures, (
        "Active verifier docs imply automatic follow-up issue creation without "
        "the manual verify:create-issue / verify:create-new-pr caveat:\n" + "\n".join(failures)
    )
