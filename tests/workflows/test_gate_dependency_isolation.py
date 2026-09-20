"""Exercise the actual Gate dependency bootstrap without installing packages."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize("prefix", ["", "templates/consumer-repo/"])
@pytest.mark.parametrize("project_file", ["pyproject.toml", "setup.py"])
@pytest.mark.parametrize("failure", ["", "missing-name", "ambiguous-name", "uninstall"])
def test_gate_removes_reported_project_or_fails_closed(tmp_path, prefix, project_file, failure):
    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load((root / prefix / ".github/workflows/pr-00-gate.yml").read_text())
    step = next(
        step
        for step in workflow["jobs"]["test-quality"]["steps"]
        if step.get("name") == "Install test-quality dependencies"
    )
    (tmp_path / project_file).write_text(
        '[project]\nname = "example-project"\n' if project_file.endswith("toml") else "# fixture\n"
    )
    report = tmp_path / "fixture-report.json"
    report.write_text(
        json.dumps(
            {
                "install": [
                    {"requested": False, "metadata": {"name": "runtime-dependency"}},
                    {
                        "requested": True,
                        "metadata": (
                            {} if failure == "missing-name" else {"name": "example-project"}
                        ),
                    },
                ]
                + (
                    [{"requested": True, "metadata": {"name": "second-project"}}]
                    if failure == "ambiguous-name"
                    else []
                )
            }
        )
    )
    log = tmp_path / "pip-calls.log"
    shim = """
python() {
  if [ "$1" = "-m" ]; then
    printf '%s\\n' "$*" >> "$PIP_TEST_LOG"
    if [ "$3" = "install" ] && [ "$4" = "--report" ]; then
      cp "$PIP_TEST_REPORT" "$5"
    fi
    if [ "$3" = "uninstall" ] && [ "$PIP_TEST_FAILURE" = "uninstall" ]; then
      return 1
    fi
    return 0
  fi
  command python3 "$@"
}
"""
    result = subprocess.run(
        ["bash", "-c", shim + step["run"]],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PIP_TEST_LOG": str(log),
            "PIP_TEST_REPORT": str(report),
            "PIP_TEST_FAILURE": failure,
        },
    )
    if failure:
        assert result.returncode != 0, "Unsafe base execution must not continue"
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        calls = log.read_text().splitlines()
        assert any(call.startswith("-m pip install --report ") for call in calls)
        assert "-m pip uninstall -y example-project" in calls
        assert "-m pip uninstall -y runtime-dependency" not in calls
