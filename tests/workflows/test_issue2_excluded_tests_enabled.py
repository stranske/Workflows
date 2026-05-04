from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_issue2_autofix_stub_modules_are_importable() -> None:
    expected_modules = (
        "scripts.fix_cosmetic_aggregate",
        "scripts.mypy_return_autofix",
        "scripts.update_autofix_expectations",
    )

    for module_name in expected_modules:
        module = importlib.import_module(module_name)
        assert callable(module.main)


def test_issue2_workflow_tests_are_not_excluded_from_ruff() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    ruff_excludes = config["tool"]["ruff"].get("exclude", [])
    assert "tests/workflows" not in ruff_excludes
    assert not any(str(path).startswith("tests/workflows/") for path in ruff_excludes)


def test_issue2_selftest_ci_runs_all_workflow_tests() -> None:
    workflow = (ROOT / ".github/workflows/selftest-ci.yml").read_text(encoding="utf-8")

    assert "python -m pytest tests/workflows/ -v" in workflow
    assert "--ignore tests/workflows" not in workflow
    assert "--ignore=tests/workflows" not in workflow
