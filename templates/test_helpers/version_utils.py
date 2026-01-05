"""Test utilities for version-agnostic dependency testing.

This module provides helpers for testing dependency compatibility without
hardcoding specific version numbers. Tests should focus on behavior and
declared version ranges, not exact versions.

Example Usage:
    >>> # Test that installed version satisfies declared range
    >>> assert_version_in_declared_range("numpy")

    >>> # Get version for conditional logic
    >>> if get_package_version("streamlit") >= Version("1.50.0"):
    ...     # Test feature only available in 1.50+

    >>> # Check all dependencies at once
    >>> assert_all_dependencies_within_ranges()
"""

from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version


def get_package_version(package: str) -> Version:
    """Get the installed version of a package.

    Args:
        package: Package name (e.g., "numpy", "streamlit")

    Returns:
        Version object for the installed package

    Raises:
        importlib.metadata.PackageNotFoundError: If package not installed
        InvalidVersion: If version string is malformed
    """
    version_str = importlib.metadata.version(package)
    return Version(version_str)


def get_declared_version_range(package: str, pyproject_path: Path | None = None) -> SpecifierSet:
    """Extract declared version range from pyproject.toml.

    Args:
        package: Package name to look up
        pyproject_path: Path to pyproject.toml (defaults to repo root)

    Returns:
        SpecifierSet representing the declared version constraint
        (e.g., SpecifierSet(">=1.2,<2.0"))

    Example:
        >>> spec = get_declared_version_range("numpy")
        >>> Version("2.3.4") in spec
        True
    """
    if pyproject_path is None:
        # Assume we're in tests/ directory
        pyproject_path = Path(__file__).parents[2] / "pyproject.toml"

    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)

    # Search in dependencies
    for dep in pyproject.get("project", {}).get("dependencies", []):
        if _is_matching_dependency(dep, package):
            return _parse_version_spec(dep)

    # Search in optional-dependencies
    for group_deps in pyproject.get("project", {}).get("optional-dependencies", {}).values():
        for dep in group_deps:
            if _is_matching_dependency(dep, package):
                return _parse_version_spec(dep)

    # No version constraint found - allow any version
    return SpecifierSet()


def assert_version_in_declared_range(package: str, pyproject_path: Path | None = None) -> None:
    """Assert that installed version satisfies declared range in pyproject.toml.

    This is the recommended way to test version compatibility. It ensures
    the installed version matches what was declared, without hardcoding
    specific version numbers.

    Args:
        package: Package name to check
        pyproject_path: Path to pyproject.toml (defaults to repo root)

    Raises:
        AssertionError: If installed version not in declared range
        importlib.metadata.PackageNotFoundError: If package not installed

    Example:
        >>> # In a test
        >>> def test_numpy_version_compatible():
        ...     assert_version_in_declared_range("numpy")
    """
    installed = get_package_version(package)
    declared = get_declared_version_range(package, pyproject_path)

    if not declared:
        # No constraint declared - any version is fine
        return

    assert installed in declared, (
        f"{package} version {installed} not in declared range {declared}. "
        f"Either update pyproject.toml or check for breaking changes."
    )


def assert_all_dependencies_within_ranges(
    pyproject_path: Path | None = None,
) -> None:
    """Assert all installed dependencies satisfy their declared ranges.

    This provides a comprehensive check that the entire dependency tree
    is consistent with pyproject.toml. Useful as a single test to catch
    lock file drift or manual installation issues.

    Args:
        pyproject_path: Path to pyproject.toml (defaults to repo root)

    Raises:
        AssertionError: If any dependency version is out of range

    Example:
        >>> def test_all_dependency_versions():
        ...     assert_all_dependencies_within_ranges()
    """
    if pyproject_path is None:
        pyproject_path = Path(__file__).parents[2] / "pyproject.toml"

    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)

    # Collect all dependency specifications
    all_deps = list(pyproject.get("project", {}).get("dependencies", []))
    for group_deps in pyproject.get("project", {}).get("optional-dependencies", {}).values():
        all_deps.extend(group_deps)

    failures = []
    for dep_spec in all_deps:
        package_name = _extract_package_name(dep_spec)
        try:
            installed = get_package_version(package_name)
            declared = _parse_version_spec(dep_spec)

            if declared and installed not in declared:
                failures.append(f"{package_name}: installed {installed} not in declared {declared}")
        except importlib.metadata.PackageNotFoundError:
            # Optional dependency not installed - skip
            pass

    assert not failures, "Dependency versions out of range:\n  " + "\n  ".join(failures)


def has_feature(package: str, min_version: str) -> bool:
    """Check if installed package version meets minimum requirement.

    Useful for conditional feature testing when a feature was added
    in a specific version.

    Args:
        package: Package name
        min_version: Minimum version required (e.g., "1.2.0")

    Returns:
        True if installed version >= min_version

    Example:
        >>> if has_feature("streamlit", "1.50.0"):
        ...     # Test features only in streamlit 1.50+
        ...     assert hasattr(st, "new_feature")
    """
    try:
        installed = get_package_version(package)
        return installed >= Version(min_version)
    except importlib.metadata.PackageNotFoundError:
        return False


# Private helpers


def _extract_package_name(dep_spec: str) -> str:
    """Extract package name from a dependency specification.

    Examples:
        "numpy>=2.0,<3.0" -> "numpy"
        "pandas[excel]>=2.0" -> "pandas"
        "pytest" -> "pytest"
    """
    # Remove extras (e.g., [excel])
    name = dep_spec.split("[")[0]

    # Remove version specifiers
    for op in ["==", ">=", "<=", ">", "<", "~=", "!="]:
        if op in name:
            name = name.split(op)[0]

    # Remove any trailing/leading whitespace or commas
    return name.strip().strip(",")


def _parse_version_spec(dep_spec: str) -> SpecifierSet:
    """Parse version specifier from dependency string.

    Examples:
        "numpy>=2.0,<3.0" -> SpecifierSet(">=2.0,<3.0")
        "pandas" -> SpecifierSet()
    """
    # Remove package name and extras
    spec_str = dep_spec.split("]", 1)[-1]  # Remove extras if present
    package_name = _extract_package_name(dep_spec)

    # Remove package name from beginning
    spec_str = spec_str.replace(package_name, "", 1).strip()

    if not spec_str:
        return SpecifierSet()

    return SpecifierSet(spec_str)


def _is_matching_dependency(dep_spec: str, package: str) -> bool:
    """Check if a dependency specification matches a package name.

    Args:
        dep_spec: Dependency specification (e.g., "numpy>=2.0")
        package: Package name to match (e.g., "numpy")

    Returns:
        True if dep_spec is for the given package
    """
    return _extract_package_name(dep_spec).lower() == package.lower()
