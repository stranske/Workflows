"""Test and script conveniences for this repository.

This module ensures the repository's ``src`` directory is available on ``sys.path``
without requiring editable installs. Python automatically imports ``sitecustomize``
when present, so keeping this lightweight avoids surprises while still allowing
local modules to be imported in tests and utility scripts.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if SRC.is_dir():
    src_str = str(SRC)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)
