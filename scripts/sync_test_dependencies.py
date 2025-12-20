"""Synchronise test imports with the dependency declarations in pyproject.toml.

The previous workflow stored test-only dependencies in requirements.txt. With the
project now using pyproject.toml as the single source of truth we ensure that any
third-party imports used by the test suite are captured inside the ``dev`` extra
and regenerate the lock file afterwards.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import tomllib
from pathlib import Path
from typing import Any, Set, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
if SRC_PATH.exists():
    sys.path.insert(0, str(SRC_PATH))


TOMLKIT_ERROR: ImportError | None
try:
    import tomlkit
except ImportError as exc:  # pragma: no cover - exercised via CLI messaging.
    TOMLKIT_ERROR = exc
else:
    TOMLKIT_ERROR = None

PYPROJECT_FILE = Path("pyproject.toml")
DEV_EXTRA = "dev"

# Stdlib modules that don't need to be installed (keep in sync with
# tests/test_dependency_enforcement.py)
STDLIB_MODULES = {
    "abc",
    "argparse",
    "ast",
    "asyncio",
    "base64",
    "builtins",
    "collections",
    "contextlib",
    "configparser",
    "copy",
    "csv",
    "datetime",
    "decimal",
    "fractions",
    "functools",
    "gc",
    "glob",
    "hashlib",
    "importlib",
    "inspect",
    "io",
    "itertools",
    "json",
    "logging",
    "math",
    "multiprocessing",
    "os",
    "pathlib",
    "pkgutil",
    "pickle",
    "platform",
    "random",
    "re",
    "runpy",
    "shlex",
    "shutil",
    "signal",
    "sitecustomize",
    "socket",
    "stat",
    "string",
    "struct",
    "subprocess",
    "sys",
    "tempfile",
    "textwrap",
    "threading",
    "time",
    "tomllib",
    "typing",
    "unittest",
    "urllib",
    "uuid",
    "warnings",
    "weakref",
    "xml",
    "zipfile",
    "__future__",
    "dataclasses",
    "enum",
    "types",
    "traceback",
    "pprint",
}

# Known test framework modules
TEST_FRAMEWORK_MODULES = {
    "pytest",
    "hypothesis",
    "_pytest",
    "pluggy",
}

# Project modules (installed via ``pip install -e .``)
PROJECT_MODULES = {
    "analysis",
    "cli",
    "trend_analysis",
    "trend_portfolio_app",
    "streamlit_app",
    "trend_model",
    "trend",
    "src",
    "data",
    "backtest",
    "app",
    "tools",
    "scripts",
    "tests",
    "utils",
    "_autofix_diag",
    "gate_summary",
    "restore_branch_snapshots",
    "test_test_dependencies",
    "decode_raw_input",
    "fallback_split",
    "parse_chatgpt_topics",
    "health_summarize",
}

# Module name to package name mappings for known exceptions
MODULE_TO_PACKAGE = {
    "yaml": "PyYAML",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "pre_commit": "pre-commit",
}


def _normalize_module_name(module: str) -> str:
    return module.replace("-", "_").lower()


def _normalise_package_name(package: str) -> str:
    """Normalise package identifiers for set comparisons."""

    return _normalize_module_name(package)


_SPECIFIER_PATTERN = re.compile(r"[!=<>~]")


def _extract_requirement_name(entry: str) -> str | None:
    """Return the canonical package name for a requirement entry."""

    cleaned = entry.split(";")[0].strip().strip(",")
    if not cleaned:
        return None

    token = cleaned.split()[0]
    if not token:
        return None

    token = token.split("[", maxsplit=1)[0]
    token = _SPECIFIER_PATTERN.split(token, maxsplit=1)[0]

    return token or None


def extract_imports_from_file(file_path: Path) -> Set[str]:
    """Extract all top-level import names from a Python file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError):
        return set()

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split(".")[0]
                imports.add(module)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module = node.module.split(".")[0]
                imports.add(module)

    return imports


def get_all_test_imports() -> Set[str]:
    """Get all imports used across all test files."""
    test_dir = Path("tests")
    if not test_dir.exists():
        return set()

    all_imports = set()
    for test_file in test_dir.rglob("*.py"):
        if "__pycache__" in str(test_file):
            continue
        imports = extract_imports_from_file(test_file)
        all_imports.update(imports)

    return all_imports


def get_declared_dependencies() -> tuple[Set[str], dict[str, list[str]]]:
    """Return declared dependency module names and raw dependency groups."""
    if not PYPROJECT_FILE.exists():
        return set(), {}

    data = tomllib.loads(PYPROJECT_FILE.read_text(encoding="utf-8"))
    project = data.get("project", {})

    declared: Set[str] = set()
    groups: dict[str, list[str]] = {}

    for entry in project.get("dependencies", []):
        package = entry.split(";")[0].strip().strip(",")
        if package:
            groups.setdefault("dependencies", []).append(package)
            name = _extract_requirement_name(package)
            if name:
                declared.add(_normalise_package_name(name))

    for group, entries in project.get("optional-dependencies", {}).items():
        groups[group] = list(entries)
        for entry in entries:
            name = _extract_requirement_name(entry)
            if name:
                declared.add(_normalise_package_name(name))

    return declared, groups


def find_missing_dependencies() -> Set[str]:
    """Find imports that are not declared as dependencies."""
    declared, _ = get_declared_dependencies()
    all_imports = get_all_test_imports()

    potential = all_imports - STDLIB_MODULES - TEST_FRAMEWORK_MODULES - PROJECT_MODULES

    missing: Set[str] = set()
    for import_name in potential:
        package_name = MODULE_TO_PACKAGE.get(import_name, import_name)
        normalised = _normalise_package_name(package_name)
        if normalised not in declared:
            missing.add(package_name)

    return missing


def add_dependencies_to_pyproject(missing: Set[str], fix: bool = False) -> bool:
    """Add missing dependencies to the dev extra inside pyproject.toml."""
    if not missing or not fix:
        return False

    if TOMLKIT_ERROR is not None:
        raise SystemExit(
            "tomlkit is required to update pyproject.toml automatically. "
            "Install the dev dependencies (pip install -e .[dev]) and retry."
        ) from TOMLKIT_ERROR

    document = tomlkit.parse(PYPROJECT_FILE.read_text(encoding="utf-8"))

    project = cast(Any, document["project"])
    optional = project.setdefault("optional-dependencies", tomlkit.table())
    dev_group = optional.get(DEV_EXTRA)
    if dev_group is None:
        dev_group = tomlkit.array()
        dev_group.multiline(True)
        optional[DEV_EXTRA] = dev_group

    existing_normalised = {_normalise_package_name(str(item).split("[")[0]) for item in dev_group}

    added = False
    for package in sorted(missing):
        normalised = _normalise_package_name(package)
        if normalised in existing_normalised:
            continue
        dev_group.append(package)
        existing_normalised.add(normalised)
        added = True

    if added:
        PYPROJECT_FILE.write_text(tomlkit.dumps(document), encoding="utf-8")

    return added


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Sync test dependencies to pyproject.toml")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Update the dev extra in pyproject.toml with missing dependencies",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Exit with code 1 if changes are needed (for CI)",
    )
    args = parser.parse_args(argv)

    missing = find_missing_dependencies()

    if not missing:
        print("✅ All test dependencies are declared in pyproject.toml")
        return 0

    print(f"⚠️  Found {len(missing)} undeclared dependencies:")
    for dep in sorted(missing):
        print(f"  - {dep}")

    if args.fix:
        added = add_dependencies_to_pyproject(missing, fix=True)
        if added:
            print("\n✅ Added dependencies to [project.optional-dependencies.dev]")
            print("Please run: make lock")
        else:
            print("\nℹ️  Dependencies already declared in dev extra")
        return 0

    if args.verify:
        print("\n❌ Run: python scripts/sync_test_dependencies.py --fix")
        return 1

    print("\nTo fix, run: python scripts/sync_test_dependencies.py --fix")
    return 0


if __name__ == "__main__":
    try:
        from trend_analysis.script_logging import setup_script_logging

        setup_script_logging(module_file=__file__)
    except ImportError:
        pass
    sys.exit(main())
