"""Exercise the documented standalone composite with ordinary rotation JSON."""

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize("prefix", [Path("."), Path("templates/consumer-repo")])
def test_export_preserves_rotation_json(prefix: Path, tmp_path: Path) -> None:
    action = prefix / ".github/actions/export-load-balancer-tokens/action.yml"
    step = yaml.safe_load(action.read_text())["runs"]["steps"][0]
    document = json.dumps({"pats": [{"id": "demo", "token": "sample"}]})
    values = {"token_rotation_json": document, "token_rotation_env_keys": "DEMO_SLOT"}

    def render(text: str) -> str:
        return re.sub(r"\$\{\{ inputs\.(\w+) \}\}", lambda m: values.get(m[1], ""), text)

    output = tmp_path / "github-env"
    environment = {name: render(value) for name, value in step.get("env", {}).items()}
    subprocess.run(
        ["bash", "-c", render(step["run"])],
        env={**environment, "GITHUB_ENV": str(output)},
        cwd=tmp_path,
        check=True,
    )
    exported = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert exported["TOKEN_ROTATION_JSON"] == document
    assert exported["TOKEN_ROTATION_ENV_KEYS"] == "DEMO_SLOT"
