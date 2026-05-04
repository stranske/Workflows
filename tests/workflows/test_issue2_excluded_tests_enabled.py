from __future__ import annotations

import importlib
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_issue2_excluded_autofix_tests_only_depend_on_local_scripts() -> None:
    excluded_test_files = (
        "tests/workflows/test_autofix_full_pipeline.py",
        "tests/workflows/test_autofix_pipeline.py",
        "tests/workflows/test_autofix_pipeline_diverse.py",
        "tests/workflows/test_autofix_pr_comment.py",
    )
    expected_imports = {
        "scripts.auto_type_hygiene",
        "scripts.build_autofix_pr_comment",
        "scripts.fix_cosmetic_aggregate",
        "scripts.fix_numpy_asserts",
        "scripts.mypy_autofix",
        "scripts.mypy_return_autofix",
        "scripts.update_autofix_expectations",
    }

    observed_imports: set[str] = set()
    pattern = re.compile(r"(?:from|import)\s+(scripts\.[a-zA-Z0-9_\.]+)")
    for relative_path in excluded_test_files:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        observed_imports.update(pattern.findall(text))

    assert observed_imports == expected_imports


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

    ruff_config = config["tool"]["ruff"]
    ruff_excludes = [
        str(path).rstrip("/")
        for key in ("exclude", "extend-exclude")
        for path in ruff_config.get(key, [])
    ]
    assert not any(
        path == "tests/workflows" or path.startswith("tests/workflows/") for path in ruff_excludes
    )


def test_issue2_selftest_ci_runs_all_workflow_tests() -> None:
    workflow = (ROOT / ".github/workflows/selftest-ci.yml").read_text(encoding="utf-8")

    assert "python -m pytest tests/workflows/ -v" in workflow
    assert not re.search(r"--ignore(?:=|\s+)tests/workflows/?(?:\s|$)", workflow)
