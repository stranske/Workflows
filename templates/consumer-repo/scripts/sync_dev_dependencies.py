#!/usr/bin/env python3
"""Sync dev tool version pins from autofix-versions.env to pyproject.toml.

This script updates the [project.optional-dependencies] dev section in pyproject.toml
to use the pinned versions from the central autofix-versions.env file.

It handles both exact pins (==) and minimum version pins (>=) in pyproject.toml,
converting them to exact pins for reproducibility.

Usage:
    python sync_dev_dependencies.py --check    # Verify versions match
    python sync_dev_dependencies.py --apply    # Update pyproject.toml
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
    # Match patterns like "package>=1.0.0" or "package==1.0.0" or just "package"
    pattern = re.compile(r'"([a-zA-Z0-9_-]+)(?:(>=|==|~=|>|<|<=|!=)([^"]+))?(?:\[.*?\])?"')

    for match in pattern.finditer(section):
        package = match.group(1)
        operator = match.group(2) or ""
        version = match.group(3) or ""
        deps.append((package, operator, version))

    return deps


def update_dependency_version(
    content: str, package: str, new_version: str, use_exact_pin: bool = True
) -> tuple[str, bool]:
    """Update a single dependency version in the content.

    Returns (new_content, was_changed).
    """
    # Pattern to match the package with any version specifier
    # Handles: "package>=1.0", "package==1.0", "package~=1.0", or just "package"
    pattern = re.compile(
        rf'"({re.escape(package)})(>=|==|~=|>|<|<=|!=)?([^"\[\]]*)?(\[.*?\])?"', re.IGNORECASE
    )

    def replacer(m: re.Match) -> str:
        pkg_name = m.group(1)
        extras = m.group(4) or ""
        op = "==" if use_exact_pin else ">="
        return f'"{pkg_name}{op}{new_version}{extras}"'

    new_content, count = pattern.subn(replacer, content)
    return new_content, count > 0


def sync_versions(
    pyproject_path: Path,
    pin_file_path: Path,
    apply: bool = False,
    use_exact_pins: bool = True,
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
