"""The supported Python floor is 3.13 (owner decision 2026-10-28: 3.14 first, 3.13 backup)."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOOR = (3, 13)
NEWEST = (3, 14)
REQUIRES = re.compile(r">=3\.13(?:,<(?P<upper>3\.\d+|4(?:\.0)?))?")
CLASSIFIER = re.compile(r"Programming Language :: Python :: (3\.\d+)")


def _version(value: object) -> tuple[int, int]:
    match = re.fullmatch(r"(?:py)?(\d)\.?(\d+)(?:\.\d+)?", str(value))
    assert match, f"unrecognised Python version {value!r}"
    return (int(match.group(1)), int(match.group(2)))


def _config() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def _assert_requires_python(project: dict) -> None:
    spec = project.get("requires-python", "").replace(" ", "")
    match = REQUIRES.fullmatch(spec)
    assert match, f"requires-python must be >=3.13 with an optional upper bound, got {spec!r}"
    upper = match.group("upper")
    if upper and upper.startswith("3."):
        assert _version(upper) > NEWEST, f"upper bound {upper} excludes Python 3.14"


def _assert_classifiers(project: dict) -> None:
    # Classifiers are optional metadata; when a repo declares versioned ones they must match the standard.
    matches = (CLASSIFIER.fullmatch(c) for c in project.get("classifiers", []))
    versions = {m.group(1) for m in matches if m}
    if versions:
        assert {"3.13", "3.14"} <= versions, f"classifiers must include 3.13 and 3.14: {versions}"
        assert all(_version(v) >= FLOOR for v in versions), f"classifier below 3.13: {versions}"


def _assert_tool_targets(tool: dict) -> None:
    # A missing key is not a regression: ruff and black infer the target from requires-python.
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


def test_python_floor_is_3_13() -> None:
    config = _config()
    project = config.get("project", {})
    _assert_requires_python(project)
    _assert_classifiers(project)
    _assert_tool_targets(config.get("tool", {}))
