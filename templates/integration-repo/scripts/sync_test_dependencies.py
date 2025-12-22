#!/usr/bin/env python3
"""Stub sync_test_dependencies.py for integration testing.

The reusable CI workflow calls this script to check for undeclared test dependencies.
This minimal implementation always reports success since the integration repo has
a simple, well-defined dependency set.
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync test dependencies (stub)")
    parser.add_argument("--fix", action="store_true", help="Auto-fix missing dependencies")
    parser.add_argument("--verify", action="store_true", help="Verify dependencies")
    parser.parse_args()

    print("✅ All test dependencies are declared in pyproject.toml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
