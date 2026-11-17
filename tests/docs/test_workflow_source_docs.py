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
AGENTS_POLICY_DOC = Path("docs/AGENTS_POLICY.md")
CI_AGENTS_POLICY_DOC = Path("docs/ci/AGENTS_POLICY.md")
WORKFLOW_SYSTEM_DOC = Path("docs/ci/WORKFLOW_SYSTEM.md")
WORKFLOW_GUIDE_DOC = Path("docs/WORKFLOW_GUIDE.md")
ACTIVE_VERIFIER_DOCS = (
    Path("README.md"),
    WORKFLOW_GUIDE_DOC,
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


def test_readme_compare_profile_semantics() -> None:
    readme = README.read_text(encoding="utf-8")
    guide = Path("docs/WORKFLOW_GUIDE.md").read_text(encoding="utf-8")
    workflow = yaml.load(
        (WORKFLOWS_DIR / "reusable-agents-verifier.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert workflow["on"]["workflow_call"]["inputs"]["evidence_profile"]["default"] == "standard"
    assert "`evidence_profile=standard` aggregates the available result rows" in readme
    assert "without requiring both configured provider slots to be present" in readme
    assert "a single completed judge can yield PASS" in readme
    assert "standard PASS alone does not prove two judges ran" in readme
    assert (
        "Reported FAIL/CONCERNS verdicts, unavailable/error results, and CI/evidence floors still withhold PASS"
        in readme
    )
    assert (
        "`evidence_profile=expanded` requires a complete, error-free boolean `used_llm=true` PASS from both provider slots"
        in readme
    )
    assert "only after a real verifier truncation report" in readme
    assert "inspect both provider results before claiming dual-model acceptance" in readme
    assert "PASS does not prove the reports contain no advisory concerns" in readme
    assert "unanimous PASS" not in readme
    # WORKFLOW_GUIDE keeps the README contract link and the real truncation-report gate.
    assert "[README comparison contract](../README.md#verification-pipeline)" in guide
    assert "If an actual verifier report identifies bounded-input truncation" in guide
    assert "inspect both provider results before" in guide
    assert "Standard remains the default" in guide


def test_agents70_docs_match_eligibility_and_dry_run() -> None:
    agents70 = yaml.safe_load(
        (WORKFLOWS_DIR / "agents-70-orchestrator.yml").read_text(encoding="utf-8")
    )
    agents70_events = agents70.get("on") or agents70.get(True) or {}
    declared_events = set(agents70_events)
    assert declared_events == {
        "schedule",
        "workflow_dispatch",
        "workflow_run",
        "repository_dispatch",
    }
    assert agents70_events["schedule"] == [{"cron": "*/30 * * * *"}]
    assert (
        str(agents70_events["workflow_dispatch"]["inputs"]["dry_run"]["default"]).lower() == "false"
    )
    assert agents70_events["workflow_run"]["workflows"] == ["Gate"]
    assert agents70_events["workflow_run"]["types"] == ["completed"]
    assert agents70_events["repository_dispatch"]["types"] == ["agents-orchestrator-ping"]

    eligibility_steps = agents70["jobs"]["eligibility"]["steps"]
    eligibility_step = next(step for step in eligibility_steps if step.get("id") == "eligibility")
    expected_actions = {
        item.strip()
        for item in eligibility_step["with"]["expected-actions"].split(",")
        if item.strip()
    }
    custom_predicate = eligibility_step["with"]["custom-predicate"]
    assert expected_actions == {"workflow_dispatch", "schedule"}
    assert "event_name == 'workflow_dispatch' || event_name == 'schedule'" in custom_predicate
    denied_events = declared_events - expected_actions
    assert denied_events == {"workflow_run", "repository_dispatch"}

    init_job = agents70["jobs"]["init"]
    assert init_job["needs"] == "eligibility"
    assert init_job["if"] == "needs.eligibility.outputs.should_run == 'true'"
    dry_run_expr = init_job["with"]["dry_run"]
    assert (
        "(github.event_name == 'schedule' || github.event_name == 'workflow_run') && 'true'"
        in dry_run_expr
    )
    assert "github.event_name == 'workflow_dispatch' && github.event.inputs.dry_run" in dry_run_expr

    keepalive_loop = yaml.safe_load(
        (WORKFLOWS_DIR / "agents-keepalive-loop.yml").read_text(encoding="utf-8")
    )
    keepalive_loop_events = keepalive_loop.get("on") or keepalive_loop.get(True) or {}
    assert keepalive_loop_events["workflow_run"]["workflows"] == ["Gate"]
    assert keepalive_loop_events["workflow_run"]["types"] == ["completed"]

    keepalive_sweep = yaml.safe_load(
        (WORKFLOWS_DIR / "agents-keepalive-sweep.yml").read_text(encoding="utf-8")
    )
    keepalive_sweep_events = keepalive_sweep.get("on") or keepalive_sweep.get(True) or {}
    assert {"schedule", "workflow_dispatch"} <= set(keepalive_sweep_events)

    policy = AGENTS_POLICY_DOC.read_text(encoding="utf-8")
    ci_policy = CI_AGENTS_POLICY_DOC.read_text(encoding="utf-8")
    workflows_doc = WORKFLOWS_DOC.read_text(encoding="utf-8")
    workflow_system_doc = WORKFLOW_SYSTEM_DOC.read_text(encoding="utf-8")
    workflow_guide_doc = WORKFLOW_GUIDE_DOC.read_text(encoding="utf-8")

    # Authoritative policy + resolving pointer without divergent active-entrypoint claims.
    assert "(`docs/AGENTS_POLICY.md`) is the single" in policy
    assert "](../AGENTS_POLICY.md)" in ci_policy
    assert (
        CI_AGENTS_POLICY_DOC.parent / "../AGENTS_POLICY.md"
    ).resolve() == AGENTS_POLICY_DOC.resolve()
    for stale_claim in (
        "single dispatch surface for all consumer",
        "as always-on automation",
        "Agents 63 – ChatGPT issue sync",
        "The first two workflows are the only active Agents entry points",
    ):
        assert stale_claim not in policy
        assert stale_claim not in ci_policy

    # Retained protection/override requirements and delete-vs-restore evidence in AGENTS_POLICY.md.
    for required_policy_phrase in (
        "## Required checks and status contexts",
        "## How to verify required checks",
        "## Allowlisted change reasons and label process",
        "## Emergency override procedure",
        "agents:allow-change",
        "uses: owner/action@ref",
        "delete-versus-restore decision",
    ):
        assert required_policy_phrase in policy

    # Catalog diagram and control-plane description in docs/ci/WORKFLOWS.md must not claim
    # Gate dispatches Agents 70.
    assert (
        'gate["Gate\\n.pr-00-gate.yml"] --> agents70["Agents 70 Orchestrator' not in workflows_doc
    )
    assert not re.search(r"gate\s*-->\s*agents70\b", workflows_doc)
    assert "Successful Gate runs dispatch the [Agents 70 Orchestrator]" not in workflows_doc
    assert "Successful Gate runs dispatch the Agents 70 Orchestrator" not in workflows_doc
    assert (
        'gate["Gate\\n.pr-00-gate.yml"] --> keepaliveLoop["Agents Keepalive Loop' in workflows_doc
    )
    assert (
        'keepaliveSweep["Agents Keepalive Sweep\\n.agents-keepalive-sweep.yml"] --> keepaliveLoop'
        in workflows_doc
    )

    # All four docs (AGENTS_POLICY, WORKFLOWS, WORKFLOW_SYSTEM, WORKFLOW_GUIDE) must align on
    # the four declared events, eligibility denial before init, forced scheduled dry_run shadow,
    # input-controlled workflow_dispatch, qualified 0ecdff0f3 attribution, keepalive loop/sweep
    # citations, authored-vs-observed separation, and the undecided retirement question.
    for doc_name, content in (
        ("docs/AGENTS_POLICY.md", policy),
        ("docs/ci/WORKFLOWS.md", workflows_doc),
        ("docs/ci/WORKFLOW_SYSTEM.md", workflow_system_doc),
        ("docs/WORKFLOW_GUIDE.md", workflow_guide_doc),
    ):
        normalized = re.sub(r"\s+", " ", content)
        for event_name in declared_events:
            assert f"`{event_name}`" in content, f"{doc_name} missing `{event_name}`"
        assert (
            "expected-actions: workflow_dispatch,schedule" in normalized
        ), f"{doc_name} must cite eligibility expected-actions"
        assert (
            "before `jobs.init`" in normalized or "before `init`" in normalized
        ), f"{doc_name} must state denied events stop before init"
        assert (
            "dry_run=true" in normalized or "Forced dry-run shadow" in normalized
        ), f"{doc_name} must document scheduled dry-run shadow behavior"
        assert (
            "inputs.dry_run" in normalized or "github.event.inputs.dry_run" in normalized
        ), f"{doc_name} must document input-controlled workflow_dispatch dry_run"
        assert "0ecdff0f3" in normalized, f"{doc_name} must cite 0ecdff0f3"
        assert "qualified" in normalized, f"{doc_name} must qualify 0ecdff0f3 attribution"
        assert (
            "agents-keepalive-loop.yml" in normalized
        ), f"{doc_name} must cite agents-keepalive-loop.yml"
        assert (
            "agents-keepalive-sweep.yml" in normalized
        ), f"{doc_name} must cite agents-keepalive-sweep.yml"
        assert (
            "production liveness" in normalized
        ), f"{doc_name} must separate authored source from production liveness"
        assert (
            "undecided" in normalized
        ), f"{doc_name} must retain the undecided retirement question"


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


def test_workflows_doc_explains_coverage_guard_tolerance_and_recovery() -> None:
    doc = WORKFLOWS_DOC.read_text(encoding="utf-8")

    assert "warn_drop" in doc
    assert "defaults to `1.0`" in doc
    assert "current < baseline - warn_drop" in doc
    assert "recovery_days" in doc
    assert "baseline - warn_drop" in doc
    assert "does not reduce the default confirmation window" in doc


def test_agent_routing_doc_covers_enabled_registry_agents() -> None:
    registry = yaml.safe_load(AGENT_REGISTRY.read_text(encoding="utf-8"))
    routing_doc = MULTI_AGENT_ROUTING_DOC.read_text(encoding="utf-8")

    active_runners = {
        agent: config["runner_workflow"]
        for agent, config in registry["agents"].items()
        if config.get("runner_workflow") and config.get("enabled", True) is not False
    }

    assert set(active_runners) == {"codex", "claude", "cursor", "gemini", "muse"}

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
