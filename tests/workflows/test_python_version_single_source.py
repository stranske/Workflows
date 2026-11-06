"""Reject runtime literals outside the shared first-party Python version policy."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / ".github/workflows/ci-python-versions.env"
VERSION = re.compile(r"(?<![\w.])3\.\d+(?:\.\d+)?(?:-dev|t)?(?![\w.])")
RUNTIME_KEY = re.compile(
    r"^(?:.*[-_])?python(?:[-_]versions?)?$|^COVERAGE_REFERENCE_RUNTIME$", re.I
)
# Only minimum-support declarations may be exempted. This universal lock targets
# the package's >=3.12 floor; it does not install/select the CI interpreter.
# Match exact path, source line and version so unrelated pins cannot piggyback.
MINIMUM_ALLOWLIST = {
    (
        ".github/workflows/maint-69-sync-integration-repo.yml",
        "uv pip compile --python-version 3.13 --upgrade pyproject.toml \\",
        "3.12",
    ),
}


def _runtime_literals(text: str) -> list[tuple[int, str]]:
    """Use YAML structure for inputs/matrices and inspect runtime flags in scripts.

    Descriptions, comments and historical artifact paths are data, not runtime
    selections. Inspect raw source spans to retain exact diagnostic line numbers.
    """
    tree = yaml.compose(text)
    found: set[tuple[int, str]] = set()
    matrix_axes = {"python", "python-version", "python_version"}

    def literals(node: ScalarNode) -> None:
        raw = text[node.start_mark.index : node.end_mark.index]
        for match in VERSION.finditer(raw):
            line = node.start_mark.line + raw[: match.start()].count("\n") + 1
            found.add((line, match.group()))

    def walk(node, runtime=False, matrix=False) -> None:
        if isinstance(node, ScalarNode):
            if runtime:
                literals(node)
                matrix_axes.update(re.findall(r"matrix\.([\w-]+)", node.value))
        elif isinstance(node, SequenceNode):
            for item in node.value:
                walk(item, runtime, matrix)
        elif isinstance(node, MappingNode):
            for key, value in node.value:
                name = key.value
                # For input definitions inspect only actual defaults/options,
                # never descriptions containing examples or support minimums.
                selected = (
                    bool(RUNTIME_KEY.fullmatch(name))
                    or (runtime and name in {"default", "options"})
                    or (matrix and name in matrix_axes)
                )
                walk(value, selected, matrix or name == "matrix")

    walk(tree)
    # A matrix axis may have an arbitrary name (e.g. matrix.interpreter) and
    # appear before its setup-python use, so resolve references in a second pass.
    walk(tree)
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("#", "//")):
            continue
        # Shell/embedded-code runtime selection: CLI flags and assignments.
        # JSON runtime keys inside a script are covered here as well.
        selection = re.search(
            r"(?:--python(?:-version)?(?:=|\s+)|"
            r"\b(?:[A-Z_]*PYTHON_VERSION[S]?|python[-_]versions?|"
            r"primary-python-version|coverage-python-version)['\"]?\s*[:=]|"
            r"\b(?:candidates|fallback)\s*=\s*\[|\bpython:)",
            line,
        )
        if selection:
            for match in VERSION.finditer(line[selection.end() :]):
                found.add((number, match.group()))
    return sorted(found)


def test_python_runtime_literals_follow_shared_env() -> None:
    pins = dict(
        line.split("=", 1)
        for line in ENV.read_text().splitlines()
        if line and not line.startswith("#")
    )
    allowed = set(pins["CI_PYTHON_VERSIONS"].split(","))
    assert allowed and all(VERSION.fullmatch(version) for version in allowed)
    assert pins["CI_PYTHON_VERSION"] in allowed
    failures = []
    for base in (ROOT, ROOT / "templates/consumer-repo"):
        paths = sorted(
            set(base.glob(".github/workflows/*.yml"))
            | set(base.glob(".github/actions/**/action.yml"))
            | set(base.glob(".github/workflow-templates/*.yml"))
        )
        assert paths, f"No workflow/action surfaces found under {base}"
        for path in paths:
            text = path.read_text()
            relative = path.relative_to(ROOT).as_posix()
            lines = text.splitlines()
            for line, version in _runtime_literals(text):
                if (relative, lines[line - 1].strip(), version) in MINIMUM_ALLOWLIST:
                    continue
                if version not in allowed:
                    failures.append(
                        f"{relative}:{line}: runtime {version}: {lines[line - 1].strip()}"
                    )
    assert not failures, "Runtime versions absent from ci-python-versions.env:\n" + "\n".join(
        failures
    )


@pytest.mark.parametrize(
    "source, expected",
    [
        ('with:\n  python-version: "3.12"\n', [(2, "3.12")]),
        ('inputs:\n  python-version:\n    default: "3.12"\n', [(3, "3.12")]),
        ('with:\n  python-versions: \'["3.12", "3.14"]\'\n', [(2, "3.12"), (2, "3.14")]),
        ('with:\n  primary-python-version: "3.12"\n', [(2, "3.12")]),
        ('env:\n  PYTHON_VERSION: "3.12"\n', [(2, "3.12")]),
        ('strategy:\n  matrix:\n    python: ["3.12", "3.14"]\n', [(3, "3.12"), (3, "3.14")]),
        (
            'matrix:\n  interpreter:\n    - "3.12"\nwith:\n'
            "  python-version: ${{ matrix.interpreter }}\n",
            [(3, "3.12")],
        ),
        ("run: |\n  uv pip compile --python-version 3.12 pyproject.toml\n", [(2, "3.12")]),
        ('run: |\n  PYTHON_VERSION="3.12"\n', [(2, "3.12")]),
        ('run: |\n  candidates = [single] if single else ["3.12"]\n', [(2, "3.12")]),
        ('run: |\n  const fallback = ["3.12"];\n', [(2, "3.12")]),
        ("container: python:3.12-slim\n", [(1, "3.12")]),
        ('# python-version: "3.12"\nname: coverage-3.12\n', []),
        ("inputs:\n  python-version:\n    description: Supports >=3.12\n", []),
    ],
)
def test_runtime_literal_extraction(source: str, expected: list[tuple[int, str]]) -> None:
    assert _runtime_literals(source) == expected
