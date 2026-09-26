"""Guard autofix-loop routing keys against selecting agent:auto as a concrete runner."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTOFIX_LOOP = ROOT / ".github/workflows/agents-autofix-loop.yml"


def test_autofix_fallback_never_selects_auto():
    text = AUTOFIX_LOOP.read_text()
    match = re.search(
        r"nonRoutingAgentKeys\s*=\s*new Set\(\[([^\]]+)\]\)",
        text,
    )
    assert match is not None, "nonRoutingAgentKeys Set not found in agents-autofix-loop.yml"
    keys = {part.strip().strip("'\"") for part in match.group(1).split(",")}
    assert "auto" in keys
