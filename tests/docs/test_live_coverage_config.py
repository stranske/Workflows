"""Validate the coverage inputs used by the Workflows test suite."""

import tomllib
from pathlib import Path


def test_workflows_coverage_measures_branches_in_core_sources() -> None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    with pyproject.open("rb") as config:
        run = tomllib.load(config)["tool"]["coverage"]["run"]

    assert run["branch"] is True
    assert run["source"] == ["scripts", "tools"]
