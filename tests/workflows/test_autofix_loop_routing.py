"""Exercise autofix-loop routing without selecting agent:auto as a runner."""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTOFIX_LOOP = ROOT / ".github/workflows/agents-autofix-loop.yml"


def _route_for(labels: list[str]) -> dict[str, object]:
    text = AUTOFIX_LOOP.read_text()
    match = re.search(
        r"(?P<routing>\s+const labels = Array\.isArray\(prData\.labels\).*?"
        r"let autofixEnabled = configMatch\s*\? configMatch\[1\].*?"
        r": hasExplicitAgentLabel;)\s+\n\s+const jobs = await",
        text,
        re.DOTALL,
    )
    assert match is not None, "routing block not found in agents-autofix-loop.yml"
    pr_data = {"labels": [{"name": label} for label in labels], "body": ""}
    script = (
        f"const prData = {json.dumps(pr_data)};\n"
        "const outputs = {};\n"
        f"{match.group('routing')}\n"
        "process.stdout.write(JSON.stringify({agentType: outputs.agent_type, autofixEnabled}));\n"
    )
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_autofix_fallback_never_selects_auto():
    assert _route_for(["agent:auto"]) == {
        "agentType": "codex",
        "autofixEnabled": False,
    }
    assert _route_for(["agent:auto", "agent:claude"]) == {
        "agentType": "claude",
        "autofixEnabled": True,
    }
