import json
import re
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


def _section(path: str, start_heading: str, end_heading: str) -> str:
    content = Path(path).read_text(encoding="utf-8")
    start = content.index(start_heading)
    end = content.index(end_heading, start)
    return content[start:end]


def test_delivery_entry_points_match_generated_delivery_review_policy() -> None:
    policy = json.loads(Path("config/consumer_sync_review_policy.json").read_text(encoding="utf-8"))
    active_mode = policy.get("generated_delivery_review")
    sections = {
        "README.md": _section("README.md", "### First-party Consumers", "## Agent Pipeline"),
        "docs/INTEGRATION_GUIDE.md": _section(
            str(GUIDE), "### Method 2: Template Workflows", "### Method 3: Hybrid Approach"
        ),
    }
    active_claim = re.compile(r"(?:currently|active value is) `([^`]+)`")
    legacy_active_claims = [
        "through bounded reviewer settlement",
        "after bounded reviewer settlement",
    ]

    for name, section in sections.items():
        flat = " ".join(section.split())
        documented = active_claim.findall(flat)
        assert documented == [active_mode], (
            f"{name} documents active delivery review {documented}, "
            f"policy generated_delivery_review is {active_mode!r}"
        )
        assert "Maint 71 is the sole merger" in flat, name
        assert "`generated_delivery_review` is absent" in flat, name
        for claim in legacy_active_claims:
            assert claim not in flat, f"{name} still claims {claim!r} is active"
        paragraphs = [" ".join(p.split()) for p in section.split("\n\n")]
        active_paragraphs = [p for p in paragraphs if active_claim.search(p)]
        assert len(active_paragraphs) == 1, name
        assert (
            "settlement" not in active_paragraphs[0].lower()
        ), f"{name} describes reviewer settlement as part of the active path"
        for paragraph in paragraphs:
            if "reviewer settlement" in paragraph.lower() or "reviewer-settlement" in paragraph:
                assert (
                    "`generated_delivery_review` is absent" in paragraph
                ), f"{name} mentions reviewer settlement outside the legacy-only scope"
        for preserved in ("CI", "Gate", "owner disposition", "exact head, source, and plan"):
            assert preserved in flat, f"{name} dropped {preserved!r}"
