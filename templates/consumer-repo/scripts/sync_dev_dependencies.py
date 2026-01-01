#!/usr/bin/env python3
"""Sync dev tool version pins from autofix-versions.env to pyproject.toml.

This script updates the [project.optional-dependencies] dev section in pyproject.toml
to use the pinned versions from the central autofix-versions.env file.

It handles both exact pins (==) and minimum version pins (>=) in pyproject.toml,
converting them to exact pins for reproducibility.

Usage:
    python sync_dev_dependencies.py --check    # Verify versions match
    python sync_dev_dependencies.py --apply    # Update pyproject.toml
    python sync_dev_dependencies.py --apply --lockfile  # Update requirements.lock too
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Default paths (can be overridden for testing)
PIN_FILE = Path(".github/workflows/autofix-versions.env")
PYPROJECT_FILE = Path("pyproject.toml")
LOCKFILE_FILE = Path("requirements.lock")

# Map env file keys to package names
# Format: ENV_KEY -> (package_name, optional_alternative_names)
# NOTE: Only include dev tools here. Runtime dependencies (hypothesis, pyyaml,
# pydantic, jsonschema) should NOT be synced - they're managed by Dependabot.
TOOL_MAPPING: dict[str, tuple[str, ...]] = {
    "RUFF_VERSION": ("ruff",),
    "BLACK_VERSION": ("black",),
    "ISORT_VERSION": ("isort",),
    "MYPY_VERSION": ("mypy",),
    "PYTEST_VERSION": ("pytest",),
    "PYTEST_COV_VERSION": ("pytest-cov",),
    "PYTEST_XDIST_VERSION": ("pytest-xdist",),
    "COVERAGE_VERSION": ("coverage",),
    "DOCFORMATTER_VERSION": ("docformatter",),
}

LOCKFILE_PATTERN = re.compile(
    r"^(?P<lead>\s*)(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^\s#]+)(?P<trail>\s*(?:#.*)?)$"
)


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse the autofix-versions.env file into a dict of key=value pairs."""
    if not path.exists():
        print(f"Warning: Pin file '{path}' not found, skipping version sync")
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    return values


def find_dev_dependencies_section(content: str) -> tuple[int, int, str] | None:
    """Find the dev dependencies section in pyproject.toml.

    Returns (start_index, end_index, section_content) or None if not found.
    """
    # Look for [project.optional-dependencies] section with dev = [...]
    # Handle both inline and multi-line formats

    # Pattern for multi-line dev dependencies
    pattern = re.compile(r"^dev\s*=\s*\[\s*\n(.*?)\n\s*\]", re.MULTILINE | re.DOTALL)

    match = pattern.search(content)
    if match:
        return match.start(), match.end(), match.group(0)

    # Try inline format: dev = ["pkg1", "pkg2"]
    inline_pattern = re.compile(r"^dev\s*=\s*\[(.*?)\]", re.MULTILINE)
    match = inline_pattern.search(content)
    if match:
        return match.start(), match.end(), match.group(0)

    return None


def extract_dependencies(section: str) -> list[tuple[str, str, str]]:
    """Extract dependencies from a dev section.

    Returns list of (package_name, operator, version) tuples.
    """
    deps = []
    # Match patterns like "package>=1.0.0", "package==1.0.0", "package", or "package[extra]==1.0.0"
    # Per PEP 508, extras come BEFORE version specifier: package[extra]>=1.0.0
    pattern = re.compile(
        r'"([a-zA-Z0-9_-]+)'  # package name
        r"(?:\[[^\]]+\])?"  # optional extras, e.g. [standard]
        r"(?:(>=|==|~=|>|<|<=|!=)"  # optional operator
        r'([^"\[\]]+))?"'  # optional version
    )

    for match in pattern.finditer(section):
        package = match.group(1)
        operator = match.group(2) or ""
        version = (match.group(3) or "").strip()
        deps.append((package, operator, version))

    return deps


def update_dependency_version(
    content: str, package: str, new_version: str, use_exact_pin: bool = True
) -> tuple[str, bool]:
    """Update a single dependency version in the content.

    Returns (new_content, was_changed).
    """
    # Pattern to match the package with any version specifier
    # Per PEP 508: extras come BEFORE version specifier (package[extra]>=1.0.0)
    pattern = re.compile(
        rf'"({re.escape(package)})(\[[^\]]+\])?(?![-\w])(>=|==|~=|>|<|<=|!=)?([^"\[\]]*)?"',
        re.IGNORECASE,
    )

    def replacer(m: re.Match) -> str:
        pkg_name = m.group(1)
        extras = m.group(2) or ""
        op = "==" if use_exact_pin else ">="
        # PEP 508: extras come BEFORE version specifier
        return f'"{pkg_name}{extras}{op}{new_version}"'

    new_content, count = pattern.subn(replacer, content)
    return new_content, count > 0


def sync_versions(
    pyproject_path: Path,
    pins: dict[str, str],
    apply: bool = False,
    use_exact_pins: bool = True,
) -> tuple[list[str], list[str]]:
    """Sync versions from pin file to pyproject.toml.

    Returns (changes_made, errors).
    """
    changes: list[str] = []
    errors: list[str] = []

    # Read pyproject.toml
    if not pyproject_path.exists():
        return [], [f"pyproject.toml not found at {pyproject_path}"]

    content = pyproject_path.read_text(encoding="utf-8")
    original_content = content

    # Find dev section
    section_info = find_dev_dependencies_section(content)
    if not section_info:
        return [], ["No dev dependencies section found in pyproject.toml"]

    # Extract current dependencies
    _, _, section = section_info
    current_deps = extract_dependencies(section)
    current_packages = {pkg.lower(): (pkg, op, ver) for pkg, op, ver in current_deps}

    # Check each pinned tool
    for env_key, package_names in TOOL_MAPPING.items():
        if env_key not in pins:
            continue

        target_version = pins[env_key]

        # Find if any of the package names exist in current deps
        for pkg_name in package_names:
            pkg_lower = pkg_name.lower()
            if pkg_lower in current_packages:
                actual_pkg, current_op, current_ver = current_packages[pkg_lower]

                # Check if version differs
                if current_ver != target_version:
                    content, changed = update_dependency_version(
                        content, actual_pkg, target_version, use_exact_pins
                    )
                    if changed:
                        op = "==" if use_exact_pins else ">="
                        changes.append(
                            f"{actual_pkg}: {current_op}{current_ver} -> {op}{target_version}"
                        )
                break

    # Apply changes if requested
    if apply and content != original_content:
        pyproject_path.write_text(content, encoding="utf-8")

    return changes, errors


def _build_lockfile_targets(pins: dict[str, str]) -> dict[str, str]:
    targets: dict[str, str] = {}
    for env_key, package_names in TOOL_MAPPING.items():
        if env_key not in pins:
            continue
        for name in package_names:
            targets[name.lower()] = pins[env_key]
    return targets


def sync_lockfile(
    lockfile_path: Path, pins: dict[str, str], apply: bool = False
) -> tuple[list[str], list[str]]:
    if not lockfile_path.exists():
        return [], []

    content = lockfile_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    targets = _build_lockfile_targets(pins)
    changes: list[str] = []
    updated_lines: list[str] = []

    for line in lines:
        match = LOCKFILE_PATTERN.match(line)
        if not match:
            updated_lines.append(line)
            continue

        name = match.group("name")
        version = match.group("version")
        target_version = targets.get(name.lower())
        if target_version and version != target_version:
            changes.append(f"requirements.lock:{name}: {version} -> =={target_version}")
            if apply:
                updated_lines.append(
                    f"{match.group('lead')}{name}=={target_version}{match.group('trail')}"
                )
            else:
                updated_lines.append(line)
        else:
            updated_lines.append(line)

    if apply:
        new_content = "\n".join(updated_lines)
        if content.endswith("\n"):
            new_content += "\n"
        if new_content != content:
            lockfile_path.write_text(new_content, encoding="utf-8")

    return changes, []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync dev dependency versions from autofix-versions.env to pyproject.toml"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if versions are in sync (exit 1 if not)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply version updates to pyproject.toml",
    )
    parser.add_argument(
        "--lockfile",
        action="store_true",
        help="Also sync requirements.lock if present",
    )
    parser.add_argument(
        "--pin-file",
        type=Path,
        default=PIN_FILE,
        help=f"Path to pin file (default: {PIN_FILE})",
    )
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=PYPROJECT_FILE,
        help=f"Path to pyproject.toml (default: {PYPROJECT_FILE})",
    )

    args = parser.parse_args(argv)

    if not args.check and not args.apply:
        parser.error("Must specify either --check or --apply")

    pins = parse_env_file(args.pin_file)
    if not pins:
        print("Error: No pins found in env file", file=sys.stderr)
        return 1

    changes, errors = sync_versions(
        args.pyproject,
        pins,
        apply=args.apply,
    )

    if args.lockfile:
        lock_changes, lock_errors = sync_lockfile(LOCKFILE_FILE, pins, apply=args.apply)
        changes.extend(lock_changes)
        errors.extend(lock_errors)

    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        return 1

    if changes:
        action = "Updated" if args.apply else "Would update"
        print(f"{action} the following dependencies:")
        for change in changes:
            print(f"  {change}")
        if args.check:
            return 1
    else:
        print("All dev dependencies are in sync")

    return 0


if __name__ == "__main__":
    sys.exit(main())
