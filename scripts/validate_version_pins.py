#!/usr/bin/env python3
"""Validate that version pins in autofix-versions.env are compatible.

This script checks that pinned versions are compatible by querying PyPI
for actual dependency requirements - no hardcoded version mappings.

Usage:
    python scripts/validate_version_pins.py [env_file]
    python scripts/validate_version_pins.py --check-all-templates
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import NamedTuple


class VersionConstraint(NamedTuple):
    """A version constraint like >=7.10.6."""

    operator: str
    version: tuple[int, ...]

    @classmethod
    def parse(cls, spec: str) -> "VersionConstraint | None":
        """Parse a constraint like '>=7.10.6'."""
        match = re.match(r"([><=!]+)\s*(\d+(?:\.\d+)*)", spec.strip())
        if not match:
            return None
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


def parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a version string like '7.13.0' into a tuple."""
    # Handle versions with extras like "7.13.0rc1"
    clean = re.match(r"(\d+(?:\.\d+)*)", version_str)
    if clean:
        return tuple(int(x) for x in clean.group(1).split("."))
    return (0,)


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


def get_package_requires(package: str, version: str) -> list[str]:
    """Query PyPI for package dependencies."""
    url = f"https://pypi.org/pypi/{package}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("info", {}).get("requires_dist") or []
    except Exception as e:
        print(f"  ⚠️  Could not fetch {package}=={version} from PyPI: {e}")
        return []


def extract_base_requirement(req: str) -> tuple[str, list[str]] | None:
    """Extract package name and version constraints from a requirement string.

    Examples:
        'coverage[toml]>=7.10.6' -> ('coverage', ['>=7.10.6'])
        'pytest>=7.0,<9' -> ('pytest', ['>=7.0', '<9'])
    """
    # Remove extras and environment markers
    req = re.sub(r"\[.*?\]", "", req)  # Remove [extras]
    req = req.split(";")[0].strip()  # Remove ; markers

    # Extract package name
    match = re.match(r"([a-zA-Z0-9_-]+)\s*(.*)", req)
    if not match:
        return None

    pkg_name = match.group(1).lower()
    constraints_str = match.group(2).strip()

    if not constraints_str:
        return (pkg_name, [])

    # Split on comma for multiple constraints
    constraints = [c.strip() for c in constraints_str.split(",") if c.strip()]
    return (pkg_name, constraints)


def check_compatibility(versions: dict[str, str]) -> list[str]:
    """Check for incompatibilities by querying actual PyPI dependencies."""
    errors = []

    # For each pinned package, check if its dependencies conflict with our pins
    for pkg, version in versions.items():
        requires = get_package_requires(pkg, version)

        for req in requires:
            parsed = extract_base_requirement(req)
            if not parsed:
                continue

            dep_name, constraints = parsed

            # Is this dependency also pinned?
            if dep_name not in versions:
                continue

            pinned_version = parse_version(versions[dep_name])

            # Check each constraint
            for constraint_str in constraints:
                constraint = VersionConstraint.parse(constraint_str)
                if constraint and not constraint.satisfied_by(pinned_version):
                    errors.append(
                        f"INCOMPATIBLE: {pkg}=={version} requires {dep_name}{constraint_str}, "
                        f"but {dep_name}=={versions[dep_name]} is pinned"
                    )

    return errors


def validate_file(path: Path) -> tuple[list[str], list[str]]:
    """Validate a single env file."""
    versions = parse_env_file(path)
    if not versions:
        return [], ["No versions found in file"]

    errors = check_compatibility(versions)
    warnings: list[str] = []
    return errors, warnings


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        check_all = True
    elif sys.argv[1] == "--check-all-templates":
        check_all = True
    else:
        check_all = False
        env_file = Path(sys.argv[1])

    if check_all:
        repo_root = Path(__file__).parent.parent
        template_files = list(repo_root.glob("templates/**/autofix-versions.env"))

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
