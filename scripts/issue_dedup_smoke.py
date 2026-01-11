#!/usr/bin/env python3
"""Entrypoint for agents-dedup smoke test."""

import sys

from scripts.cli_handler import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
