"""The Workflows repo type-checks exactly the paths it declares (round-2 C1).

#5402 moved four metrics modules from src/ to scripts/metrics/. Gate's mypy step
hard-coded `src`, and `scripts.*` is `ignore_errors`, so the four modules dropped out
of strict checking while Gate stayed green. These gates keep the declared scope, the
Gate call and the reusable step's target resolution in agreement.
"""

from __future__ import annotations

import os
import stat
import subprocess
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REUSABLE = ROOT / ".github/workflows/reusable-10-ci-python.yml"
GATE = ROOT / ".github/workflows/pr-00-gate.yml"
METRICS_MODULES = {
    "scripts/metrics/aggregator.py",
    "scripts/metrics/cli_parser.py",
    "scripts/metrics/ndjson_parser.py",
    "scripts/metrics/percentile_calculator.py",
}


def _gate_typecheck_paths() -> list[str]:
    gate = yaml.safe_load(GATE.read_text(encoding="utf-8"))
    return str(gate["jobs"]["python-ci"]["with"]["typecheck-paths"]).split()


def _mypy_config() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["mypy"]


def test_gate_checks_what_pyproject_declares_and_every_path_exists() -> None:
    paths = _gate_typecheck_paths()
    assert paths == _mypy_config()["files"]
    assert "scripts/metrics" in paths
    missing = [path for path in paths if not (ROOT / path).exists()]
    assert missing == [], f"Gate would silently drop {missing} from mypy"


def test_metrics_modules_are_strict_despite_the_scripts_override() -> None:
    overrides = _mypy_config()["overrides"]
    metrics = [item for item in overrides if "scripts.metrics.*" in item["module"]]
    assert len(metrics) == 1
    assert metrics[0]["ignore_errors"] is False
    assert {str(p.relative_to(ROOT)) for p in (ROOT / "scripts/metrics").glob("*.py")} >= (
        METRICS_MODULES
    )


def _mypy_step_script() -> str:
    workflow = yaml.safe_load(REUSABLE.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["typecheck-mypy"]["steps"]
    return next(step for step in steps if step.get("id") == "mypy")["run"]


def _run_step(tmp_path: Path, typecheck_paths: str) -> tuple[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "mypy"
    fake.write_text('#!/bin/sh\necho "MYPY ARGS: $*"\n', encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    work = tmp_path / "repo"
    (work / "scripts/metrics").mkdir(parents=True)
    for module in sorted(METRICS_MODULES):
        (work / module).write_text("", encoding="utf-8")
    result = subprocess.run(
        ["bash", "-c", _mypy_step_script()],
        cwd=work,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "INPUT_TYPECHECK_PATHS": typecheck_paths,
        },
        check=True,
        text=True,
        capture_output=True,
    )
    lines = result.stdout.splitlines()
    args = next(line for line in lines if line.startswith("MYPY ARGS: "))
    return "\n".join(lines), args


def test_step_checks_and_names_every_declared_metrics_file(tmp_path) -> None:
    out, args = _run_step(tmp_path, " ".join(_gate_typecheck_paths()))
    assert args.endswith(" scripts/metrics"), args
    listed = {line.split("mypy file: ", 1)[1] for line in out.splitlines() if "mypy file: " in line}
    assert listed == METRICS_MODULES


def test_step_default_keeps_consumer_behaviour(tmp_path) -> None:
    # Consumers do not pass typecheck-paths: `src`, else the repository root.
    out, args = _run_step(tmp_path, "src")
    assert args.endswith(" ."), args
    assert "requested path 'src' does not exist" in out
