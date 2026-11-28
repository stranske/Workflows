#!/usr/bin/env python3
"""Check the integration project's lock and direct dependency-version assertions."""

import ast
import re
import shlex
import tomllib
from pathlib import Path

VERSION_MODULES = {"importlib.metadata", "importlib_metadata"}


def check_lock_file() -> list[str]:
    """Verify the generated uv lock records the extras and covers the direct declarations."""
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    lock = Path("requirements.lock")
    if not lock.exists():
        if Path(".github/workflows/maint-dependabot-auto-lock.yml").exists():
            return ["requirements.lock is missing"]
        # The freshly rendered fixture has no tracked lock or lock workflow.
        print("Skipping lock checks for the unlocked integration fixture")
        return []

    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.utils import canonicalize_name

    groups = project.get("optional-dependencies", {})
    lines = lock.read_text(encoding="utf-8").splitlines()
    command = next(
        (line[1:].strip() for line in lines if line.startswith("#") and "uv pip compile " in line),
        "",
    )
    if not command:
        return ["requirements.lock has no uv pip compile header"]
    args = shlex.split(command)
    extras = {arg.removeprefix("--extra=") for arg in args if arg.startswith("--extra=")}
    extras.update(
        value for flag, value in zip(args[:-1], args[1:], strict=True) if flag == "--extra"
    )
    issues: list[str] = []
    if "--all-extras" not in args:
        issues.extend(
            f"requirements.lock header is missing --extra {group}"
            for group in sorted(groups.keys() - extras)
        )

    pins: dict[str, set[str]] = {}
    for line in lines:
        if not line.strip() or line.lstrip().startswith(("#", "-")):
            continue
        try:
            requirement = Requirement(line.strip())
        except InvalidRequirement:
            return [f"requirements.lock contains an invalid requirement: {line.strip()}"]
        for specifier in requirement.specifier:
            if specifier.operator == "==" and "*" not in specifier.version:
                pins.setdefault(canonicalize_name(requirement.name), set()).add(specifier.version)

    declared = set(project.get("dependencies", []))
    for requirements in groups.values():
        declared.update(requirements)
    for entry in sorted(declared):
        requirement = Requirement(entry)
        versions = pins.get(canonicalize_name(requirement.name), set())
        if not versions:
            issues.append(f"requirements.lock has no pin for {requirement.name}")
        elif not any(
            requirement.specifier.contains(version, prereleases=True) for version in versions
        ):
            issues.append(
                f"requirements.lock pins {', '.join(sorted(versions))} for {requirement.name}, incompatible with {entry}"
            )
    return issues


def version_functions(tree: ast.Module) -> set[str]:
    functions = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for imported in node.names:
                if imported.name in VERSION_MODULES:
                    functions.add(f"{imported.asname or imported.name}.version")
        if isinstance(node, ast.ImportFrom):
            for imported in node.names:
                if node.module in VERSION_MODULES and imported.name == "version":
                    functions.add(imported.asname or imported.name)
                if node.module == "importlib" and imported.name == "metadata":
                    functions.add(f"{imported.asname or imported.name}.version")
    return functions


def is_version_lookup(node: ast.expr, functions: set[str]) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == "__version__") or (
        isinstance(node, ast.Call) and ast.unparse(node.func) in functions
    )


def is_version_literal(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and re.match(r"v?\d+(?:[.!+a-z]|$)", node.value, flags=re.IGNORECASE) is not None
    )


def check_version_assertions() -> list[str]:
    issues = []
    for path in sorted(Path("tests").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        functions = version_functions(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assert):
                continue
            for comparison in ast.walk(node.test):
                if not isinstance(comparison, ast.Compare):
                    continue
                operands = [comparison.left, *comparison.comparators]
                for left, operator, right in zip(
                    operands[:-1], comparison.ops, operands[1:], strict=True
                ):
                    if not isinstance(operator, ast.Eq):
                        continue
                    if (is_version_lookup(left, functions) and is_version_literal(right)) or (
                        is_version_lookup(right, functions) and is_version_literal(left)
                    ):
                        issues.append(f"{path}:{comparison.lineno}: hardcoded dependency version")
    return issues


def main() -> int:
    try:
        issues = check_lock_file() + check_version_assertions()
    except (OSError, ValueError, KeyError, SyntaxError, ImportError) as exc:
        print(f"Dependency setup cannot be checked: {exc}")
        return 1

    for issue in issues:
        print(issue)
    if issues:
        return 1
    print("Integration dependency setup checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
