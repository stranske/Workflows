"""AGENTS.md and CLAUDE.md state one repository contract.

CLAUDE.md is a full copy rather than a pointer because other tests and the Claude Code loader
read it as a complete document. The two files were kept in step by hand until the 2026-11-28
cohesion review found the only guard was a sentence asking people to do so. This test is the
guard: everything above the agent-specific note must be identical, and only the title and the
note itself may differ.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NOTE_HEADINGS = {
    "AGENTS.md": "## Agent-Specific Note",
    "CLAUDE.md": "## Claude-Specific Note",
}


def _shared_body(name: str) -> list[str]:
    lines = (REPO_ROOT / name).read_text(encoding="utf-8").splitlines()
    heading = NOTE_HEADINGS[name]
    assert lines[0].startswith(f"# {name} - "), f"{name}: first line must be its title"
    assert lines.count(heading) == 1, f"{name}: needs exactly one {heading!r}"
    return lines[1 : lines.index(heading)]


def test_agents_and_claude_share_one_contract_body() -> None:
    agents = _shared_body("AGENTS.md")
    claude = _shared_body("CLAUDE.md")
    assert len(agents) > 50, "shared body unexpectedly short"
    assert agents == claude, "AGENTS.md and CLAUDE.md differ above the agent-specific note"


def test_each_agent_note_points_at_the_other_file() -> None:
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    claude = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "`CLAUDE.md`" in agents.split(NOTE_HEADINGS["AGENTS.md"])[1]
    assert "`AGENTS.md`" in claude.split(NOTE_HEADINGS["CLAUDE.md"])[1]
