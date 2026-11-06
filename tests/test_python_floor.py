"""The supported Python floor is 3.13 (owner decision 2026-10-28: 3.14 first, 3.13 backup)."""

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLOOR = (3, 13)
NEWEST = (3, 14)
REQUIRES = re.compile(r">=3\.13(?:,<(?P<upper>3\.\d+|4(?:\.0)?))?")
CLASSIFIER = re.compile(r"Programming Language :: Python :: (3\.\d+)")


def _version(value: object) -> tuple[int, int]:
    match = re.fullmatch(r"(?:py)?(\d)\.?(\d+)(?:\.\d+)?", str(value))
    assert match, f"unrecognised Python version {value!r}"
    return (int(match.group(1)), int(match.group(2)))


# The root project plus any packaged sub-projects (for example packages/*/pyproject.toml).
PYPROJECTS = [ROOT / "pyproject.toml", *sorted(ROOT.glob("packages/*/pyproject.toml"))]


def _config(path: Path) -> dict:
    return tomllib.loads(path.read_text())


def _assert_requires_python(project: dict) -> None:
    spec = project.get("requires-python", "").replace(" ", "")
    match = REQUIRES.fullmatch(spec)
    assert match, f"requires-python must be >=3.13 with an optional upper bound, got {spec!r}"
    upper = match.group("upper")
    if upper and upper.startswith("3."):
        assert _version(upper) > NEWEST, f"upper bound {upper} excludes Python 3.14"


def _assert_classifiers(project: dict) -> None:
    # Classifiers are optional metadata; versioned ones, when declared, must match the standard.
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
    for path in PYPROJECTS:
        config = _config(path)
        project = config.get("project", {})
        _assert_requires_python(project)
        _assert_classifiers(project)
        _assert_tool_targets(config.get("tool", {}))


# The repo's own pyproject only reaches the accepting paths; the rejecting ones are pinned here.
@pytest.mark.parametrize(
    "spec,accepted",
    [
        (">=3.13", True),
        (">=3.13,<3.15", True),
        (">=3.13,<4", True),
        (">=3.13,<3.14", False),
        (">=3.12", False),
        (">=3.14", False),
    ],
)
def test_requires_python_bounds(spec: str, accepted: bool) -> None:
    if accepted:
        _assert_requires_python({"requires-python": spec})
    else:
        with pytest.raises(AssertionError):
            _assert_requires_python({"requires-python": spec})


@pytest.mark.parametrize(
    "classifiers,accepted",
    [
        (
            ["Programming Language :: Python :: 3.13", "Programming Language :: Python :: 3.14"],
            True,
        ),
        ([], True),
        (["Programming Language :: Python :: 3.14"], False),
        (
            [
                "Programming Language :: Python :: 3.12",
                "Programming Language :: Python :: 3.13",
                "Programming Language :: Python :: 3.14",
            ],
            False,
        ),
    ],
)
def test_classifier_checks(classifiers: list[str], accepted: bool) -> None:
    if accepted:
        _assert_classifiers({"classifiers": classifiers})
    else:
        with pytest.raises(AssertionError):
            _assert_classifiers({"classifiers": classifiers})


@pytest.mark.parametrize(
    "tool,accepted",
    [
        (
            {"ruff": {"target-version": "py313"}, "black": {"target-version": ["py313", "py314"]}},
            True,
        ),
        ({"mypy": {"python_version": "3.14"}}, True),
        ({"ruff": {"target-version": "py312"}}, False),
        ({"black": {"target-version": ["py311", "py313"]}}, False),
        ({"black": {"target-version": []}}, False),
        ({"mypy": {"python_version": "3.12"}}, False),
    ],
)
def test_tool_target_checks(tool: dict, accepted: bool) -> None:
    if accepted:
        _assert_tool_targets(tool)
    else:
        with pytest.raises(AssertionError):
            _assert_tool_targets(tool)
