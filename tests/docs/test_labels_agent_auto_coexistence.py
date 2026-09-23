"""Pin the `agent:auto` co-presence contract in both label guides.

The `agent:auto` section says the label is ADDED alongside a concrete `agent:<name>` label and
wins over it: since #2268 `keepalive_loop.js` drops the concrete label from routing when
`agent:auto` is present. Three other places in the same file said the opposite ("do not combine",
"switch only after removing the concrete label", and two interaction-matrix rows calling the pair
"Invalid mixed routing"), and the lane automations that followed those rows stripped `agent:auto`
off PRs. These tests make the statements agree and fail if the contradiction returns on any line
that names `agent:auto`. Two CONCRETE labels are still invalid mixed routing, and that row stays.
"""

from __future__ import annotations

from pathlib import Path

import pytest

GUIDES = (Path("docs/LABELS.md"), Path("templates/consumer-repo/docs/LABELS.md"))
FORBIDDEN_NEXT_TO_AUTO = (
    "invalid mixed routing",
    "do not combine",
    "only after removing the concrete",
    "before using `agent:auto`",
)


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    end = text.find("\n### ", start + len(heading))
    return text[start:] if end == -1 else text[start:end]


@pytest.mark.parametrize("guide", GUIDES, ids=str)
def test_agent_auto_section_states_co_presence(guide: Path) -> None:
    section = _section(guide.read_text(encoding="utf-8"), "### `agent:auto`")
    assert "alongside the existing `agent:<name>` label" in section
    assert "`agent:auto` always wins" in section
    assert "uses the available concrete label as the initial seed" in section


@pytest.mark.parametrize("guide", GUIDES, ids=str)
def test_lifecycle_and_rate_limit_guidance_keep_the_concrete_label(guide: Path) -> None:
    text = guide.read_text(encoding="utf-8")
    auto = _section(text, "### `agent:auto`")
    assert "Applied at PR creation by the opener lane" in auto
    rate_limited = _section(text, "### `agent:rate-limited`")
    assert "add `agent:auto` alongside the concrete label" in rate_limited


@pytest.mark.parametrize("guide", GUIDES, ids=str)
def test_no_line_naming_agent_auto_forbids_co_presence(guide: Path) -> None:
    offending = [
        f"{guide}:{number}: {line.strip()}"
        for number, line in enumerate(guide.read_text(encoding="utf-8").splitlines(), start=1)
        if "agent:auto" in line and any(phrase in line.lower() for phrase in FORBIDDEN_NEXT_TO_AUTO)
    ]
    assert offending == [], "agent:auto co-presence contradicted:\n" + "\n".join(offending)


@pytest.mark.parametrize("guide", GUIDES, ids=str)
@pytest.mark.parametrize("concrete", ("agent:codex", "agent:claude"))
def test_interaction_matrix_row_matches_the_section(guide: Path, concrete: str) -> None:
    rows = [
        line.strip()
        for line in guide.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith(f"| `{concrete}` | `agent:auto` |")
    ]
    assert len(rows) == 1, rows
    assert "`agent:auto` wins" in rows[0]
    assert "seeds initial selection" in rows[0]
    assert "keep both labels" in rows[0]


@pytest.mark.parametrize("guide", GUIDES, ids=str)
def test_two_concrete_labels_remain_invalid_mixed_routing(guide: Path) -> None:
    rows = [
        line.strip()
        for line in guide.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("| `agent:codex` | `agent:claude` |")
    ]
    assert len(rows) == 1, rows
    assert "Invalid mixed routing" in rows[0]
