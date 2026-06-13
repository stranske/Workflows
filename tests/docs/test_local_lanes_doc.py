"""Guard the local opener/closer lane contract doc and its enablers (issue #2280).

Covers the observable acceptance gates: the owning doc exists with its required
sections, `workloop-state.md` is ignored fleet-wide via the consumer-template
status block, and GITNEXUS.md links to the new contract doc.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_LANES = REPO_ROOT / "docs" / "ops" / "LOCAL_LANES.md"
CONSUMER_GITIGNORE = REPO_ROOT / "templates" / "consumer-repo" / ".gitignore"
GITNEXUS = REPO_ROOT / "docs" / "ops" / "GITNEXUS.md"

# The four required section headings from the issue acceptance criteria.
REQUIRED_HEADINGS = [
    "## State locations",
    "## Worktree retention tiers",
    "## `workloop-state.md` strategy",
    "## `Workflows-steward` arrangement",
]


def test_local_lanes_doc_exists_and_is_substantive() -> None:
    assert LOCAL_LANES.exists(), "docs/ops/LOCAL_LANES.md must exist"
    text = LOCAL_LANES.read_text(encoding="utf-8")
    # Scaffold-only completion does not count: require real content.
    assert len(text) > 1500, "LOCAL_LANES.md must be substantive, not a skeleton"


def test_local_lanes_doc_has_all_required_sections() -> None:
    text = LOCAL_LANES.read_text(encoding="utf-8").lower()
    missing = [h for h in REQUIRED_HEADINGS if h.lower() not in text]
    assert not missing, f"LOCAL_LANES.md missing required section(s): {missing}"


def test_workloop_state_ignored_in_consumer_template_block() -> None:
    text = CONSUMER_GITIGNORE.read_text(encoding="utf-8")
    assert "# BEGIN WORKFLOWS STATUS FILES" in text
    assert "# END WORKFLOWS STATUS FILES" in text
    begin = text.index("# BEGIN WORKFLOWS STATUS FILES")
    end = text.index("# END WORKFLOWS STATUS FILES")
    block = text[begin:end]
    assert "workloop-state.md" in block, (
        "workloop-state.md must be inside the managed status-file block so "
        "sync_status_file_ignores.py delivers it to consumer repos"
    )


def test_status_ignore_sync_script_carries_workloop_state_pattern() -> None:
    from scripts import sync_status_file_ignores

    assert "workloop-state.md" in sync_status_file_ignores.CANONICAL_PATTERNS
    assert "workloop-state.md" in sync_status_file_ignores.FALLBACK_PATTERNS


def test_gitnexus_links_to_local_lanes() -> None:
    text = GITNEXUS.read_text(encoding="utf-8")
    assert "LOCAL_LANES.md" in text, "GITNEXUS.md must link to the lane contract doc"
    # The misleading throwaway framing must be corrected.
    assert "temporary automation state and must be ignored" not in text


def test_agent_instructions_carry_steward_contract() -> None:
    for path in (REPO_ROOT / "AGENTS.md", REPO_ROOT / "CLAUDE.md"):
        text = path.read_text(encoding="utf-8")
        assert "LOCAL_LANES.md" in text
        assert "detached HEAD" in text
        assert "temporary automation state and must be ignored" not in text
