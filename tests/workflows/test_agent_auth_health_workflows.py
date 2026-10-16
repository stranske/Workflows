"""Cursor and Muse each need a presence check that names a missing secret and never echoes it."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECKS = {
    "CURSOR_API_KEY": ROOT / ".github/workflows/health-cursor-auth-check.yml",
    "META_API_KEY": ROOT / ".github/workflows/health-muse-auth-check.yml",
}


def test_each_secret_backed_agent_has_a_presence_check_that_never_echoes_the_key():
    for secret, path in CHECKS.items():
        assert path.exists(), f"{path.name} is missing"
        text = path.read_text()
        doc = yaml.safe_load(text)
        on = doc.get("on") or doc[True]
        assert "schedule" in on and "workflow_dispatch" in on, path.name
        # the only secret the workflow reads is the agent's own key
        assert set(re.findall(r"secrets\.([A-Z0-9_]+)", text)) == {secret}, path.name
        # the value is never printed or written anywhere: no echo/printf/cat/tee of $SECRET
        leaks = re.findall(rf"(?:echo|printf|cat|tee)[^\n]*\$\{{?{secret}\b", text)
        assert not leaks, f"{path.name} prints the secret: {leaks}"
        assert "${{ secrets." + secret + " }}" in text, path.name
        assert "exit 1" in text, f"{path.name} must fail loudly when the key is missing"


def test_muse_check_is_never_billable():
    text = CHECKS["META_API_KEY"].read_text()
    assert "muse exec" not in text.replace("No `muse exec`", "").replace(
        "No `muse exec` is run", ""
    )
    assert "muse --version" in text
    assert "bwrap" in text
