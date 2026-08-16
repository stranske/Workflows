from pathlib import Path

GUIDE = Path("templates/consumer-repo/docs/CI_SYSTEM_GUIDE.md")


def test_consumer_ci_guide_matches_current_agent_entrypoints() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    assert GUIDE.as_posix() == "templates/consumer-repo/docs/CI_SYSTEM_GUIDE.md"

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
