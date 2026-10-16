"""Issue intake must route the LABELLED agent, not codex (Workflows#3930).

Runs the real `Normalize inputs` step of agents-63-issue-intake.yml under bash with an
`issues` event payload, so a hard-coded default would fail here.
"""

import json
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
INTAKE = ROOT / ".github/workflows/agents-63-issue-intake.yml"


def _normalize_script() -> str:
    jobs = yaml.safe_load(INTAKE.read_text())["jobs"]
    steps = jobs["normalize_inputs"]["steps"]
    return next(s["run"] for s in steps if s.get("id") == "normalize")


def _run(tmp_path: Path, labels: list[str], env_extra: dict | None = None) -> dict:
    event = {"issue": {"number": 7, "labels": [{"name": n} for n in labels]}}
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event))
    out = tmp_path / "out.txt"
    out.write_text("")
    env = {
        "PATH": os.environ["PATH"],
        "GITHUB_EVENT_NAME": "issues",
        "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_OUTPUT": str(out),
    }
    env.update(env_extra or {})
    subprocess.run(["bash", "-c", _normalize_script()], env=env, check=True, capture_output=True)
    return dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)


def test_intake_routes_the_labelled_agent_not_codex(tmp_path):
    assert _run(tmp_path, ["agent:cursor"])["bridge_agent"] == "cursor"
    assert _run(tmp_path, ["agent:muse"])["bridge_agent"] == "muse"
    assert _run(tmp_path, ["agent:codex"])["bridge_agent"] == "codex"
    assert _run(tmp_path, ["bug"])["bridge_agent"] == "codex"  # no agent label: unchanged default


def test_post_agent_comment_is_the_neutral_name_and_post_codex_comment_still_works(tmp_path):
    neutral = _run(tmp_path, ["agent:cursor"], {"INPUT_POST_AGENT_COMMENT": "false"})
    assert neutral["post_agent_comment"] == "false"
    legacy = _run(tmp_path, ["agent:cursor"], {"INPUT_POST_CODEX_COMMENT": "false"})
    assert legacy["post_agent_comment"] == "false"
    assert legacy["post_codex_comment"] == "false"
    default = _run(tmp_path, ["agent:cursor"])
    assert default["post_agent_comment"] == "true"


def test_bridge_receives_the_neutral_output():
    text = INTAKE.read_text()
    assert "post_agent_comment: ${{ needs.normalize_inputs.outputs.post_agent_comment }}" in text
