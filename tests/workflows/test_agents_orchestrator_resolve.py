from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "orchestrator"
HARNESS = FIXTURES_DIR / "resolve_harness.js"


def _require_node() -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js is required for orchestrator resolver tests")


def _run_resolver(name: str) -> dict:
    _require_node()
    scenario_path = FIXTURES_DIR / f"{name}.json"
    assert scenario_path.exists(), f"Scenario fixture missing: {scenario_path}"
    command = ["node", str(HARNESS), str(scenario_path)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.fail(
            "Resolver harness failed with code %s:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (result.returncode, result.stdout, result.stderr)
        )
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:  # pragma: no cover - harness should return valid JSON
        pytest.fail(f"Invalid harness output: {exc}: {result.stdout}")


def test_resolver_retains_keepalive_options() -> None:
    data = _run_resolver("options_passthrough")
    outputs = data["outputs"]

    assert outputs["enable_keepalive"] == "true"
    assert outputs["keepalive_trace"] == "trace-from-options"
    assert outputs["keepalive_round"] == "7"
    assert outputs["keepalive_pr"] == "4001"

    options = json.loads(outputs["options_json"])
    assert options["keepalive_trace"] == "trace-from-options"
    assert options["round"] == "7"
    assert options["pr"] == 4001
    assert options["keepalive_instruction"].startswith("@codex") or options.get(
        "keepalive_instruction_template", ""
    ).startswith("@codex")
