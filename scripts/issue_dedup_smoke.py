#!/usr/bin/env python3
"""Create GitHub issues for agents-dedup smoke testing."""

from __future__ import annotations

import sys

from scripts.cli_handler import main

if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main(sys.argv[1:]))
