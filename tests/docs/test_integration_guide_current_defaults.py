from pathlib import Path

GUIDE = Path("docs/INTEGRATION_GUIDE.md")


def _quick_setup_section() -> str:
    content = GUIDE.read_text(encoding="utf-8")
    start = content.index("### Quick Setup")
    end = content.index("### Workflow Summary", start)
    return content[start:end]


def _workflow_summary_section() -> str:
    content = GUIDE.read_text(encoding="utf-8")
    start = content.index("### Workflow Summary")
    end = content.index("### Consolidated Workflow Migration", start)
    return content[start:end]


def test_integration_guide_quick_setup_uses_current_consumer_defaults() -> None:
    section = _quick_setup_section()

    expected_defaults = [
        "agents-issue-intake.yml",
        "agents-80-pr-event-hub.yml",
        "agents-81-gate-followups.yml",
        "agents-verifier.yml",
        "autofix.yml",
        "pr-00-gate.yml",
        "AGENTS.md",
        "CLAUDE.md",
    ]

    for filename in expected_defaults:
        assert filename in section

    assert "agents-orchestrator.yml -o .github/workflows/agents-orchestrator.yml" not in section
    assert "agents-pr-meta.yml -o .github/workflows/agents-pr-meta.yml" not in section


def test_integration_guide_workflow_summary_matches_agent_docs_defaults() -> None:
    section = _workflow_summary_section()

    for filename in [
        "agents-80-pr-event-hub.yml",
        "agents-81-gate-followups.yml",
        "agents-verifier.yml",
        "pr-00-gate.yml",
        "AGENTS.md",
        "CLAUDE.md",
    ]:
        assert filename in section

    assert "agents-orchestrator.yml" not in section
    assert "agents-pr-meta.yml" not in section
