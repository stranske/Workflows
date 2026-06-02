"""Tests for baseline_kit.catalog."""

from __future__ import annotations

from pathlib import Path

import pytest
from baseline_kit import load_catalog


def test_load_catalog_mapping(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yml"
    catalog.write_text("scenario:\n  weight: 0\n  enabled: false\n")

    assert load_catalog(catalog) == {"scenario": {"weight": 0, "enabled": False}}


def test_load_catalog_empty_file_defaults_to_empty_mapping(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yml"
    catalog.write_text("")

    assert load_catalog(catalog) == {}


@pytest.mark.parametrize("content", ["[]\n", "0\n", "false\n"])
def test_load_catalog_rejects_non_mapping_roots(tmp_path: Path, content: str) -> None:
    catalog = tmp_path / "catalog.yml"
    catalog.write_text(content)

    with pytest.raises(ValueError, match="mapping at the top level"):
        load_catalog(catalog)
