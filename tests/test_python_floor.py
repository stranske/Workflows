"""The supported Python floor is 3.13 (owner decision 2026-10-28: 3.14 first, 3.13 backup)."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOOR = (3, 13)
REQUIRES = re.compile(r">=3\.13(,<3\.\d+)?")
CLASSIFIER = re.compile(r"Programming Language :: Python :: (3\.\d+)")


def _version(value: object) -> tuple[int, int]:
    match = re.fullmatch(r"(?:py)?3\.?(\d+)(?:\.\d+)?", str(value))
    assert match, f"unrecognised Python target {value!r}"
    return (3, int(match.group(1)))


def _config() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def test_python_floor_is_3_13() -> None:
    project = _config().get("project", {})
    spec = project.get("requires-python", "").replace(" ", "")
    assert REQUIRES.fullmatch(spec), f"requires-python must be >=3.13, got {spec!r}"
    matches = (CLASSIFIER.fullmatch(c) for c in project.get("classifiers", []))
    versions = {m.group(1) for m in matches if m}
    if versions:
        assert {"3.13", "3.14"} <= versions, f"classifiers must include 3.13 and 3.14: {versions}"
        assert all(_version(v) >= FLOOR for v in versions), f"classifier below 3.13: {versions}"


def test_tool_targets_are_at_least_3_13() -> None:
    tool = _config().get("tool", {})
    targets = {}
    if "target-version" in tool.get("ruff", {}):
        targets["ruff"] = [tool["ruff"]["target-version"]]
    if "target-version" in tool.get("black", {}):
        targets["black"] = tool["black"]["target-version"]
    if "python_version" in tool.get("mypy", {}):
        targets["mypy"] = [tool["mypy"]["python_version"]]
    for name, values in targets.items():
        assert values, f"{name} target list is empty"
        assert all(_version(v) >= FLOOR for v in values), f"{name} targets below 3.13: {values}"
