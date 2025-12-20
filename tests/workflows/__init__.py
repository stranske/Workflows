"""Workflow and CI automation tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

for path in (SRC, ROOT):
    path_str = str(path)
    if path.is_dir() and path_str not in sys.path:
        sys.path.insert(0, path_str)
