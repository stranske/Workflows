#!/usr/bin/env python3
"""Validate that version pins in autofix-versions.env are compatible.

This script checks for known dependency conflicts between pinned versions.
Run this before syncing versions to consumer repos.

Usage:
    python scripts/validate_version_pins.py [env_file]
    python scripts/validate_version_pins.py --check-all-templates
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple


class VersionConstraint(NamedTuple):
    """A version constraint like >=7.10.6."""

    operator: str
    version: tuple[int, ...]

    @classmethod
    def parse(cls, spec: str) -> "VersionConstraint":
        """Parse a constraint like '>=7.10.6'."""
        match = re.match(r"([><=!]+)(\d+(?:\.\d+)*)", spec)
        if not match:
            raise ValueError(f"Invalid constraint: {spec}")
        op, ver = match.groups()
        return cls(op, tuple(int(x) for x in ver.split(".")))

    def satisfied_by(self, version: tuple[int, ...]) -> bool:
        """Check if a version satisfies this constraint."""
        # Normalize lengths for comparison
        max_len = max(len(self.version), len(version))
        v1 = self.version + (0,) * (max_len - len(self.version))
        v2 = version + (0,) * (max_len - len(version))

        if self.operator == ">=":
            return v2 >= v1
        if self.operator == ">":
            return v2 > v1
        if self.operator == "<=":
            return v2 <= v1
        if self.operator == "<":
            return v2 < v1
        if self.operator == "==":
            return v2 == v1
        if self.operator == "!=":
            return v2 != v1
        return False


# Known dependency constraints between packages
# Format: {package: {dependent_package: constraint_on_package}}
KNOWN_CONSTRAINTS = {
    "coverage": {
        "pytest-cov>=7.0.0": ">=7.10.6",
        "pytest-cov>=6.0.0": ">=7.5.0",
    },
    "pydantic-core": {
        "pydantic>=2.10.0": ">=2.27.0",
        "pydantic>=2.0.0": ">=2.0.0",
    },
}


def parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a version string like '7.13.0' into a tuple."""
    return tuple(int(x) for x in version_str.split("."))


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse an autofix-versions.env file."""
    versions = {}
    if not path.exists():
        return versions

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            # Convert KEY_VERSION to package name
            pkg_name = key.replace("_VERSION", "").lower().replace("_", "-")
            versions[pkg_name] = value
    return versions


def check_compatibility(versions: dict[str, str]) -> list[str]:
    """Check for known incompatibilities."""
    errors = []

    for pkg, constraints in KNOWN_CONSTRAINTS.items():
        if pkg not in versions:
            continue

        pkg_version = parse_version(versions[pkg])

        for dependent_spec, constraint_spec in constraints.items():
            # Parse dependent package and its minimum version
            match = re.match(r"([a-z-]+)([><=!]+.+)", dependent_spec)
            if not match:
                continue
            dep_pkg, dep_constraint_str = match.groups()

            if dep_pkg not in versions:
                continue

            dep_version = parse_version(versions[dep_pkg])
            dep_constraint = VersionConstraint.parse(dep_constraint_str)

            # Check if the dependent package version triggers this constraint
            if dep_constraint.satisfied_by(dep_version):
                # Check if our package version satisfies the requirement
                req_constraint = VersionConstraint.parse(constraint_spec)
                if not req_constraint.satisfied_by(pkg_version):
                    errors.append(
                        f"INCOMPATIBLE: {dep_pkg}=={versions[dep_pkg]} requires "
                        f"{pkg}{constraint_spec}, but {pkg}=={versions[pkg]} is pinned"
                    )

    return errors


def check_missing_pins(versions: dict[str, str]) -> list[str]:
    """Check for missing pins that should be present."""
    warnings = []

    # If pytest-cov is pinned, coverage should be too
    if "pytest-cov" in versions and "coverage" not in versions:
        warnings.append(
            "WARNING: pytest-cov is pinned but coverage is not. "
            "This may cause dependency conflicts with fallback versions."
        )

    # If pydantic is pinned, pydantic-core should be too
    if "pydantic" in versions and "pydantic-core" not in versions:
        pydantic_ver = parse_version(versions["pydantic"])
        if pydantic_ver >= (2, 0, 0):
            warnings.append(
                "WARNING: pydantic>=2.0 is pinned but pydantic-core is not. "
                "This may cause dependency conflicts."
            )

    return warnings


def validate_file(path: Path) -> tuple[list[str], list[str]]:
    """Validate a single env file."""
    versions = parse_env_file(path)
    errors = check_compatibility(versions)
    warnings = check_missing_pins(versions)
    return errors, warnings


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        # Default: check all template files
        check_all = True
    elif sys.argv[1] == "--check-all-templates":
        check_all = True
    else:
        check_all = False
        env_file = Path(sys.argv[1])

    if check_all:
        # Find all autofix-versions.env files in templates
        repo_root = Path(__file__).parent.parent
        template_files = list(repo_root.glob("templates/**/autofix-versions.env"))

        # Also check the main .github/workflows version
        main_env = repo_root / ".github/workflows/autofix-versions.env"
        if main_env.exists():
            template_files.append(main_env)

        all_errors = []
        all_warnings = []

        for f in template_files:
            print(f"Checking {f.relative_to(repo_root)}...")
            errors, warnings = validate_file(f)
            if errors:
                for e in errors:
                    print(f"  ❌ {e}")
                all_errors.extend(errors)
            if warnings:
                for w in warnings:
                    print(f"  ⚠️  {w}")
                all_warnings.extend(warnings)
            if not errors and not warnings:
                print("  ✅ OK")

        if all_errors:
            print(f"\n{len(all_errors)} error(s) found!")
            return 1
        if all_warnings:
            print(f"\n{len(all_warnings)} warning(s) - consider fixing")
        return 0
    else:
        errors, warnings = validate_file(env_file)
        for e in errors:
            print(f"❌ {e}")
        for w in warnings:
            print(f"⚠️  {w}")
        return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
