from __future__ import annotations

import ast
import fnmatch
import importlib
import json
import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

HISTORIC_EXCLUDED_WORKFLOW_PATHS = (
    "tests/workflows/test_autofix_full_pipeline.py",
    "tests/workflows/test_autofix_pipeline.py",
    "tests/workflows/test_autofix_pipeline_diverse.py",
    "tests/workflows/test_autofix_pipeline_live_docs.py",
    "tests/workflows/test_autofix_pipeline_tools.py",
    "tests/workflows/test_autofix_pr_comment.py",
    "tests/workflows/test_autofix_probe_module.py",
    "tests/workflows/test_autofix_repo_regressions.py",
    "tests/workflows/test_autofix_samples.py",
    "tests/workflows/test_chatgpt_topics_parser.py",
)


def _script_imports_from(source: str) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names if alias.name.startswith("scripts."))
        elif isinstance(node, ast.ImportFrom):
            if node.module == "scripts":
                imports.update(f"scripts.{alias.name}" for alias in node.names)
            elif node.module and node.module.startswith("scripts."):
                imports.add(node.module)
    return imports


def _ruff_pattern_matches_path(pattern: str, relative_path: str) -> bool:
    normalized_pattern = pattern.rstrip("/")
    normalized_path = relative_path.rstrip("/")
    path_parts = Path(normalized_path).parts

    return (
        normalized_pattern == normalized_path
        or normalized_path.startswith(f"{normalized_pattern}/")
        or fnmatch.fnmatchcase(normalized_path, normalized_pattern)
        or Path(normalized_path).match(normalized_pattern)
        or (
            "/" not in normalized_pattern
            and fnmatch.fnmatchcase(path_parts[-1], normalized_pattern)
        )
    )


def test_issue2_excluded_autofix_tests_only_depend_on_local_scripts() -> None:
    contract = json.loads(
        (ROOT / "tests/workflows/fixtures/issue2_autofix_import_contract.json").read_text(
            encoding="utf-8"
        )
    )
    excluded_test_files = tuple(contract["import_contract_test_files"])
    expected_imports = set(contract["expected_script_imports"])

    observed_imports: set[str] = set()
    for relative_path in excluded_test_files:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        observed_imports.update(_script_imports_from(text))

    assert observed_imports == expected_imports


def test_issue2_historic_excluded_set_matches_contract() -> None:
    contract = json.loads(
        (ROOT / "tests/workflows/fixtures/issue2_autofix_import_contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert tuple(contract["historically_excluded_test_files"]) == HISTORIC_EXCLUDED_WORKFLOW_PATHS


def test_issue2_historic_excluded_files_remain_pytest_discoverable() -> None:
    contract = json.loads(
        (ROOT / "tests/workflows/fixtures/issue2_autofix_import_contract.json").read_text(
            encoding="utf-8"
        )
    )
    for relative_path in contract["import_contract_test_files"]:
        path = ROOT / relative_path
        assert path.is_file()
        assert path.suffix == ".py"
        assert path.name.startswith("test_")
        assert Path(relative_path).parts[:2] == ("tests", "workflows")


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
    assert not any(
        _ruff_pattern_matches_path(pattern, historic_path)
        for pattern in ruff_excludes
        for historic_path in HISTORIC_EXCLUDED_WORKFLOW_PATHS
    )


def test_issue2_selftest_ci_runs_all_workflow_tests() -> None:
    workflow_config = yaml.safe_load(
        (ROOT / ".github/workflows/selftest-ci.yml").read_text(encoding="utf-8")
    )
    python_test_steps = [
        step.get("run", "")
        for step in workflow_config["jobs"]["test-python"]["steps"]
        if step.get("name") == "Run Python tests"
    ]

    assert python_test_steps == ["python -m pytest tests/workflows/ -v\n"]
    assert not re.search(
        r"--ignore(?:-glob)?(?:=|\s+)tests/workflows/?(?:\s|$)", python_test_steps[0]
    )
