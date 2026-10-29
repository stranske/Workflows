"""The supported Python floor is 3.13 (owner decision 2026-10-28: 3.14 first, 3.13 backup)."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_python_floor_is_3_13() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    project = data.get("project", {})
    assert project.get("requires-python", "").replace(" ", "").startswith(">=3.13")
    assert not [c for c in project.get("classifiers", []) if c.endswith("Python :: 3.12")]
    tool = data.get("tool", {})
    targets = [str(tool.get("ruff", {}).get("target-version", ""))]
    targets += [str(item) for item in tool.get("black", {}).get("target-version", [])]
    assert "py312" not in targets
    assert tool.get("mypy", {}).get("python_version", "3.13") != "3.12"
