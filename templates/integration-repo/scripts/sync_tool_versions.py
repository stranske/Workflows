#!/usr/bin/env python3
"""Stub sync_tool_versions.py for integration testing.

The reusable CI workflow may call this script to verify tool version alignment.
This minimal implementation always reports success.
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync tool versions (stub)")
    parser.add_argument("--check", action="store_true", help="Check tool versions")
    parser.add_argument("--apply", action="store_true", help="Apply version updates")
    parser.parse_args()

    print("✅ Tool versions are aligned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
