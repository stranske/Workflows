#!/usr/bin/env python3
"""Capture the focused bootstrap-label pytest transcript for PR evidence."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/bootstrap-label-tests.txt"),
        help="Path that receives combined pytest stdout and stderr.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/scripts/test_bootstrap_consumer_labels.py",
            "-q",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(completed.stdout, encoding="utf-8")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
