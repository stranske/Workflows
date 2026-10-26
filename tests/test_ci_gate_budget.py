"""Lock Gate's parallel pytest invocation without narrowing suite discovery."""

import shlex
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_gate_pytest_args_are_parallel() -> None:
    gate = yaml.safe_load((ROOT / ".github/workflows/pr-00-gate.yml").read_text())
    inputs = gate["jobs"]["python-ci"]["with"]
    args = shlex.split(inputs["pytest_args"])
    assert args[:2] == ["-n", "auto"]
    # Only scheduling and optional timing flags: no paths, markers or deselection.
    assert args[2:] in (
        ["--dist", "load"],
        ["--dist", "load", "--durations=40", "--durations-min=5"],
    )
    assert inputs["coverage-min"] == "70"
