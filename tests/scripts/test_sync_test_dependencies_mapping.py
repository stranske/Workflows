from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_exceptions_map_to_package_names_in_repo_script():
    module = _load_module(
        "sync_test_dependencies_repo",
        Path("scripts/sync_test_dependencies.py"),
    )

    assert module.MODULE_TO_PACKAGE["pptx"] == "python-pptx"
    assert module.MODULE_TO_PACKAGE["docx"] == "python-docx"
    assert module.MODULE_TO_PACKAGE["jwt"] == "PyJWT"
    assert {"html", "http", "secrets"}.issubset(module.STDLIB_MODULES)


def test_import_exceptions_map_to_package_names_in_consumer_template():
    module = _load_module(
        "sync_test_dependencies_consumer_template",
        Path("templates/consumer-repo/scripts/sync_test_dependencies.py"),
    )

    assert module.MODULE_TO_PACKAGE["pptx"] == "python-pptx"
    assert module.MODULE_TO_PACKAGE["docx"] == "python-docx"
    assert module.MODULE_TO_PACKAGE["jwt"] == "PyJWT"


def test_python_docx_import_is_not_reported_as_undeclared(tmp_path, monkeypatch):
    """A test importing ``docx`` with ``python-docx`` declared must not be flagged.

    The import name and the distribution name differ, which is the whole reason
    MODULE_TO_PACKAGE exists. Without the entry the checker reports ``docx`` as
    undeclared, the auto-fix step exits 1, and the consumer's Python CI fails on
    a dependency that is in fact declared.
    """
    module = _load_module(
        "sync_test_dependencies_repo_docx",
        Path("scripts/sync_test_dependencies.py"),
    )

    test_file = tmp_path / "test_uses_docx.py"
    test_file.write_text("from docx import Document\n", encoding="utf-8")

    imports = module.extract_imports_from_file(test_file)
    assert "docx" in imports

    declared = {module._normalise_package_name("python-docx")}
    missing = {
        name
        for name in imports
        if module._normalise_package_name(module.MODULE_TO_PACKAGE.get(name, name))
        not in declared
    }
    assert missing == set()


def test_stdlib_imports_from_sync_pr_logs_are_ignored_in_repo_script():
    module = _load_module(
        "sync_test_dependencies_repo_stdlib",
        Path("scripts/sync_test_dependencies.py"),
    )

    assert {"email", "html", "http", "secrets"}.issubset(module.STDLIB_MODULES)


def test_stdlib_imports_from_sync_pr_logs_are_ignored_in_consumer_template():
    module = _load_module(
        "sync_test_dependencies_consumer_template_stdlib",
        Path("templates/consumer-repo/scripts/sync_test_dependencies.py"),
    )

    assert {"email", "html", "http", "secrets"}.issubset(module.STDLIB_MODULES)


def test_base_project_modules_exclude_retired_trend_packages_in_source_and_template():
    removed = {"trend_portfolio_app", "trend_model"}
    scripts = {
        "repo": Path("scripts/sync_test_dependencies.py"),
        "consumer_template": Path("templates/consumer-repo/scripts/sync_test_dependencies.py"),
    }

    for name, path in scripts.items():
        module = _load_module(f"sync_test_dependencies_{name}_retired_packages", path)
        assert module._BASE_PROJECT_MODULES.isdisjoint(removed)
