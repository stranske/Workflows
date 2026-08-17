from pathlib import Path

GUIDE = Path("templates/consumer-repo/docs/CI_SYSTEM_GUIDE.md")


def test_consumer_ci_guide_matches_current_agent_entrypoints() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    assert text.count("agents-80-pr-event-hub.yml") == 1

    for current_surface in (
        "agents-issue-intake.yml",
        "agents-71-codex-belt-dispatcher.yml",
        "agents-72-codex-belt-worker-dispatch.yml",
        "agents-80-pr-event-hub.yml",
        "agents-81-gate-followups.yml",
        "agents-verifier.yml",
    ):
        assert current_surface in text

    for retired_claim in (
        "Agents 63 Issue Intake",
        "Agents 70 Orchestrator",
        "Agents 71-73 Codex Belt",
        "Conveyor merges",
    ):
        assert retired_claim not in text

    assert "Bootstrap creates ready branch + PR" in text
    assert "guarded exact-head closer" in text
    assert "same head for at least seven minutes" in text
    assert "active non-outdated review threads" in text
    assert "bound to the validated head SHA" in text


def test_consumer_operator_docs_match_gate_followup_topology() -> None:
    labels = Path("docs/LABELS.md").read_text(encoding="utf-8")
    template_labels = Path("templates/consumer-repo/docs/LABELS.md").read_text(encoding="utf-8")
    setup = Path("templates/consumer-repo/docs/SETUP_CHECKLIST.md").read_text(encoding="utf-8")

    assert labels == template_labels
    for retired_surface in (
        "agents-63-issue-intake.yml",
        "agents-70-orchestrator.yml",
    ):
        assert retired_surface not in labels

    assert "no Cursor runner job" in labels
    assert "no Gemini runner job" in labels
    assert "Consolidated consumer: does not set `force_retry`" in labels
    assert "Root/non-consolidated: sets `force_retry=true`" in labels
    assert ".github/workflows/agents-keepalive-loop.yml" in labels
    assert "Optional recovery-request marker" in setup
    assert "USE_CONSOLIDATED_WORKFLOWS` is `true`" in setup
    assert "cleared by Agents 81 after it successfully merges" in labels
