#!/usr/bin/env python3
"""Sync dev tool version pins from autofix-versions.env to pyproject.toml.

This script updates the [project.optional-dependencies] dev section in pyproject.toml
to use the pinned versions from the central autofix-versions.env file.

It handles both exact pins (==) and minimum version pins (>=) in pyproject.toml,
converting them to exact pins for reproducibility.

If no dev dependencies section exists, it can create one with --create-if-missing.

Usage:
    python sync_dev_dependencies.py --check           # Verify versions match
    python sync_dev_dependencies.py --apply           # Update pyproject.toml
    python sync_dev_dependencies.py --apply --create-if-missing  # Create dev deps if missing
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Default paths (can be overridden for testing)
PIN_FILE = Path(".github/workflows/autofix-versions.env")
PYPROJECT_FILE = Path("pyproject.toml")

# Map env file keys to package names
# Format: ENV_KEY -> (package_name, optional_alternative_names)
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
    "HYPOTHESIS_VERSION": ("hypothesis",),
}

# Core dev tools to include when creating a new dev section
# (subset of TOOL_MAPPING - only the most essential ones)
CORE_DEV_TOOLS = [
    "RUFF_VERSION",
    "MYPY_VERSION",
    "PYTEST_VERSION",
    "PYTEST_COV_VERSION",
]


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


def find_optional_dependencies_section(content: str) -> int | None:
    """Find the [project.optional-dependencies] section header.

    Returns the index after the section header, or None if not found.
    """
    pattern = re.compile(r"^\[project\.optional-dependencies\]\s*$", re.MULTILINE)
    match = pattern.search(content)
    if match:
        return match.end()
    return None


def find_project_section_end(content: str) -> int | None:
    """Find a good place to insert [project.optional-dependencies].

    Returns the index after the [project] section ends (before next section).
    """
    # Find [project] section
    project_match = re.search(r"^\[project\]\s*$", content, re.MULTILINE)
    if not project_match:
        return None

    # Find the next section header after [project]
    next_section = re.search(r"^\[", content[project_match.end() :], re.MULTILINE)
    if next_section:
        return project_match.end() + next_section.start()

    # No next section, return end of content
    return len(content)


def create_dev_dependencies_section(pins: dict[str, str], use_exact_pins: bool = True) -> str:
    """Create a new dev dependencies section with core tools."""
    op = "==" if use_exact_pins else ">="
    deps = []

    for env_key in CORE_DEV_TOOLS:
        if env_key in pins:
            pkg_name = TOOL_MAPPING[env_key][0]
            version = pins[env_key]
            deps.append(f'    "{pkg_name}{op}{version}",')

    if not deps:
        return ""

    return "dev = [\n" + "\n".join(deps) + "\n]"


def extract_dependencies(section: str) -> list[tuple[str, str, str]]:
    """Extract dependencies from a dev section.

    Returns list of (package_name, operator, version) tuples.
    """
    deps = []
    # Match patterns like "package>=1.0.0" or "package==1.0.0" or just "package"
    # Be precise: package name followed by optional version specifier
    pattern = re.compile(r'"([a-zA-Z0-9_-]+)(?:(>=|==|~=|>|<|<=|!=)([^"\[\]]+))?(?:\[.*?\])?"')

    for match in pattern.finditer(section):
        package = match.group(1)
        operator = match.group(2) or ""
        version = match.group(3) or ""
        deps.append((package, operator, version))

    return deps


def update_dependency_in_section(
    section: str, package: str, new_version: str, use_exact_pin: bool = True
) -> tuple[str, bool]:
    """Update a single dependency version within a section.

    IMPORTANT: This only updates exact package name matches, not partial matches.
    For example, "pytest" will NOT match "pytest-cov" or "pytest-xdist".

    Returns (new_section, was_changed).
    """
    # Pattern to match EXACT package name with any version specifier
    # The key is using word boundaries and ensuring we match the exact package
    # Pattern: "package" or "package>=version" or "package[extras]>=version"
    # We need to be careful not to match "pytest" when looking at "pytest-cov"

    # Match: "package" + optional version spec, NOT followed by more pkg name chars
    # The negative lookahead (?!-) ensures we don't match "pytest" in "pytest-cov"
    pattern = re.compile(
        rf'"({re.escape(package)})(?![-\w])(>=|==|~=|>|<|<=|!=)?([^"\[\]]*)?(\[.*?\])?"',
        re.IGNORECASE,
    )

    def replacer(m: re.Match) -> str:
        pkg_name = m.group(1)
        extras = m.group(4) or ""
        op = "==" if use_exact_pin else ">="
        return f'"{pkg_name}{op}{new_version}{extras}"'

    new_section, count = pattern.subn(replacer, section)
    return new_section, count > 0


def sync_versions(
    pyproject_path: Path,
    pin_file_path: Path,
    apply: bool = False,
    use_exact_pins: bool = True,
    create_if_missing: bool = False,
) -> tuple[list[str], list[str]]:
    """Sync versions from pin file to pyproject.toml.

    Returns (changes_made, errors).
    """
    changes: list[str] = []
    errors: list[str] = []

    # Parse pin file
    pins = parse_env_file(pin_file_path)
    if not pins:
        return [], ["No pins found in env file"]

    # Read pyproject.toml
    if not pyproject_path.exists():
        return [], [f"pyproject.toml not found at {pyproject_path}"]

    content = pyproject_path.read_text(encoding="utf-8")
    original_content = content

    # Find dev section
    section_info = find_dev_dependencies_section(content)

    if not section_info:
        if not create_if_missing:
            return [], ["No dev dependencies section found in pyproject.toml"]

        # Create new dev dependencies section
        new_section = create_dev_dependencies_section(pins, use_exact_pins)
        if not new_section:
            return [], ["Could not create dev dependencies section - no pins available"]

        # Find where to insert
        opt_deps_pos = find_optional_dependencies_section(content)
        if opt_deps_pos is not None:
            # Add after [project.optional-dependencies] header
            content = content[:opt_deps_pos] + "\n" + new_section + "\n" + content[opt_deps_pos:]
        else:
            # Need to add [project.optional-dependencies] section
            insert_pos = find_project_section_end(content)
            if insert_pos is None:
                return [], ["Could not find [project] section to add optional-dependencies"]

            section_to_add = "\n[project.optional-dependencies]\n" + new_section + "\n"
            content = content[:insert_pos] + section_to_add + content[insert_pos:]

        op = "==" if use_exact_pins else ">="
        for env_key in CORE_DEV_TOOLS:
            if env_key in pins:
                pkg_name = TOOL_MAPPING[env_key][0]
                changes.append(f"{pkg_name}: (new) -> {op}{pins[env_key]}")

        if apply:
            pyproject_path.write_text(content, encoding="utf-8")

        return changes, errors

    # Extract the section boundaries and content
    section_start, section_end, section = section_info

    # Extract current dependencies from the section
    current_deps = extract_dependencies(section)
    current_packages = {pkg.lower(): (pkg, op, ver) for pkg, op, ver in current_deps}

    # Work on a copy of just the section
    new_section = section

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
                    new_section, changed = update_dependency_in_section(
                        new_section, actual_pkg, target_version, use_exact_pins
                    )
                    if changed:
                        op = "==" if use_exact_pins else ">="
                        changes.append(
                            f"{actual_pkg}: {current_op}{current_ver} -> {op}{target_version}"
                        )
                break

    # Replace the section in the full content
    if new_section != section:
        content = content[:section_start] + new_section + content[section_end:]

    # Apply changes if requested
    if apply and content != original_content:
        pyproject_path.write_text(content, encoding="utf-8")

    return changes, errors


def main() -> int:
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
        "--create-if-missing",
        action="store_true",
        help="Create dev dependencies section if it doesn't exist",
    )
    parser.add_argument(
        "--use-minimum-pins",
        action="store_true",
        help="Use >= instead of == for version pins",
    )
    parser.add_argument(
        "--pin-file",
        type=Path,
        default=PIN_FILE,
        help="Path to the version pins file",
    )
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=PYPROJECT_FILE,
        help="Path to pyproject.toml",
    )

    args = parser.parse_args()

    if args.check and args.apply:
        parser.error("--check and --apply are mutually exclusive")

    if not args.check and not args.apply:
        args.check = True  # Default to check mode

    use_exact_pins = not args.use_minimum_pins

    changes, errors = sync_versions(
        args.pyproject,
        args.pin_file,
        apply=args.apply,
        use_exact_pins=use_exact_pins,
        create_if_missing=args.create_if_missing,
    )

    if errors:
        for err in errors:
            print(f"Error: {err}", file=sys.stderr)
        return 2

    if changes:
        print(f"{'Applied' if args.apply else 'Found'} {len(changes)} version updates:")
        for change in changes:
            print(f"  - {change}")

        if args.check:
            print("\nRun with --apply to update pyproject.toml")
            return 1
        else:
            print("\n✓ pyproject.toml updated")
            return 0
    else:
        print("✓ All dev dependency versions are in sync")
        return 0


if __name__ == "__main__":
    sys.exit(main())
