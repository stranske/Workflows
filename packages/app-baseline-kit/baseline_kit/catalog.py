"""Catalog loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml


def load_catalog(path: str | Path) -> dict[str, Any]:
    """Load a scenario catalog YAML file into a dict."""
    with Path(path).open() as fh:
        loaded = yaml.safe_load(fh)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError("Catalog YAML must contain a mapping at the top level.")
    return cast(dict[str, Any], loaded)
