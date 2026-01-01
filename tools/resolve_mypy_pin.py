#!/usr/bin/env python3
"""Resolve which Python version should run mypy.

This script outputs a single Python version to GITHUB_OUTPUT to ensure mypy
only runs once per CI matrix (avoiding duplicate type-checking across Python
versions).

The script:
1. Reads the target Python version from pyproject.toml's [tool.mypy] section
2. Falls back to the first version in the CI matrix
3. Outputs the resolved version to GITHUB_OUTPUT for workflow use
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_mypy_python_version() -> str | None:
    """Extract python_version from pyproject.toml's [tool.mypy] section."""
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        return None

    try:
        # Try tomlkit first (more accurate TOML parsing)
        import tomlkit

        content = pyproject_path.read_text()
        data = tomlkit.parse(content)
        tool_raw = data.get("tool")
        # Use dict() to normalize tomlkit types and satisfy mypy
        # tomlkit returns Table objects that act like dicts but mypy doesn't know this
        tool: dict[str, object] = dict(tool_raw) if hasattr(tool_raw, "get") else {}  # type: ignore[arg-type,call-overload]
        mypy_raw = tool.get("mypy")
        mypy: dict[str, object] = dict(mypy_raw) if hasattr(mypy_raw, "get") else {}  # type: ignore[arg-type,call-overload]
        version = mypy.get("python_version")
        # Validate type before conversion - TOML can parse various types
        if isinstance(version, (str, int, float)):
            return str(version)
        return None
    except ImportError:
        pass

    # Fallback: simple regex-based extraction
    import re

    content = pyproject_path.read_text()
    # Match python_version in [tool.mypy] section
    match = re.search(
        r'\[tool\.mypy\].*?python_version\s*=\s*["\']?(\d+\.\d+)["\']?',
        content,
        re.DOTALL,
    )
    if match:
        return match.group(1)

    return None


def main() -> int:
    """Determine and output the Python version for mypy."""
    # Get the current matrix Python version from environment
    matrix_version = os.environ.get("MATRIX_PYTHON_VERSION", "")

    # Get the mypy-configured Python version from pyproject.toml
    mypy_version = get_mypy_python_version()

    # Determine which version to output
    # If mypy has a configured version, use it; otherwise use matrix version
    if mypy_version:  # noqa: SIM108
        output_version = mypy_version
    else:
        # Default to the primary Python version (first in typical matrices)
        output_version = matrix_version or "3.11"

    # Write to GITHUB_OUTPUT
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"python-version={output_version}\n")
        print(f"Resolved mypy Python version: {output_version}")
    else:
        # For local testing
        print(f"python-version={output_version}")

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
