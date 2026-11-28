"""Maint 71 auto-fix formats WIT with WIT's own pinned black/ruff (cohesion review B10).

It used to run `pip install black ruff`, so a direct push to WIT's default branch could
reformat with versions newer than the ones WIT's CI checks against.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/maint-71-auto-fix-integration.yml"


def _install_step() -> dict:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["detect-and-fix"]["steps"]
    return next(step for step in steps if step.get("name") == "Install formatting tools")


def _run(tmp_path: Path, env_text: str | None) -> tuple[subprocess.CompletedProcess[str], str]:
    pins = tmp_path / "integration-tests/.github/workflows/autofix-versions.env"
    if env_text is not None:
        pins.parent.mkdir(parents=True)
        pins.write_text(env_text, encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    record = tmp_path / "pip-args"
    shim = bin_dir / "python3"
    shim.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "{record}"\n', encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    result = subprocess.run(
        ["bash", "-c", str(_install_step()["run"])],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result, record.read_text(encoding="utf-8") if record.exists() else ""


def test_install_pins_black_and_ruff_from_the_wit_env_file(tmp_path: Path) -> None:
    result, args = _run(
        tmp_path, "# pins\nBLACK_VERSION=26.10.1\nRUFF_VERSION=0.17.6\nMYPY_VERSION=2.4.1\n"
    )
    assert result.returncode == 0, result.stderr
    assert args.split() == ["-m", "pip", "install", "black==26.10.1", "ruff==0.17.6"]


def test_install_refuses_without_the_pin_file(tmp_path: Path) -> None:
    result, args = _run(tmp_path, None)
    assert result.returncode != 0
    assert "refusing to format with unpinned tools" in result.stdout
    assert args == ""


def test_install_refuses_a_missing_or_malformed_pin(tmp_path: Path) -> None:
    result, args = _run(tmp_path, "BLACK_VERSION=latest\nRUFF_VERSION=0.17.6\n")
    assert result.returncode != 0
    assert "BLACK_VERSION" in result.stderr
    assert args == ""


def test_no_unpinned_install_remains() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pip install black ruff" not in text
