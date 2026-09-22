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
        "ci.yml",
        "autofix-versions.env",
        "agents-issue-intake.yml",
        "agents-80-pr-event-hub.yml",
        "agents-81-gate-followups.yml",
        "agents-verifier.yml",
        "autofix.yml",
        "pr-00-gate.yml",
        "AGENTS.md",
        "CLAUDE.md",
        "docs/TARGET_WORK_ENVIRONMENT.md",
    ]

    for filename in expected_defaults:
        assert filename in section

    legacy_defaults = [
        "agents-orchestrator.yml -o .github/workflows/agents-orchestrator.yml",
        "agents-pr-meta.yml -o .github/workflows/agents-pr-meta.yml",
    ]
    for legacy_entry in legacy_defaults:
        assert legacy_entry not in section

    assert "mkdir -p docs" in section
    assert (
        "templates/consumer-repo/docs/TARGET_WORK_ENVIRONMENT.md "
        "-o docs/TARGET_WORK_ENVIRONMENT.md"
    ) in section
    assert section.count("docs/TARGET_WORK_ENVIRONMENT.md") == 2


def test_integration_guide_workflow_summary_matches_agent_docs_defaults() -> None:
    section = _workflow_summary_section()

    for filename in [
        "agents-80-pr-event-hub.yml",
        "agents-81-gate-followups.yml",
        "agents-verifier.yml",
        "pr-00-gate.yml",
        "AGENTS.md",
        "CLAUDE.md",
        "docs/TARGET_WORK_ENVIRONMENT.md",
    ]:
        assert filename in section

    assert "agents-orchestrator.yml" not in section
    assert "agents-pr-meta.yml" not in section
    assert section.count("docs/TARGET_WORK_ENVIRONMENT.md") == 1


def test_integration_guide_migration_table_marks_legacy_replacements() -> None:
    content = GUIDE.read_text(encoding="utf-8")
    start = content.index("### Consolidated Workflow Migration")
    end = content.index("### Required Secrets", start)
    section = content[start:end]

    assert "Legacy workflow files may still exist during migrations" in section
    assert "| `agents-pr-meta.yml` | `agents-80-pr-event-hub.yml` |" in section
    assert "| `agents-keepalive-loop.yml` | `agents-81-gate-followups.yml` |" in section
