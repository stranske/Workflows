"""Catalog loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_catalog(path: str | Path) -> dict[str, Any]:
    """Load a scenario catalog YAML file into a dict."""
    with Path(path).open() as fh:
        return yaml.safe_load(fh)
