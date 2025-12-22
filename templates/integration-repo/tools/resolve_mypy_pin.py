#!/usr/bin/env python3
"""Stub resolve_mypy_pin.py for integration testing.

The reusable CI workflow calls this script to determine which Python version
should run mypy. This minimal implementation outputs the current matrix version.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    # Get the current matrix Python version from environment
    matrix_version = os.environ.get("MATRIX_PYTHON_VERSION", "3.11")

    # Write to GITHUB_OUTPUT
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"python-version={matrix_version}\n")
        print(f"Resolved mypy Python version: {matrix_version}")
    else:
        # For local testing
        print(f"python-version={matrix_version}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
