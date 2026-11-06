"""Shared tools and templates must not carry Python 3.12 (3.14 first, 3.13 backup).

The reusable CI pins are guarded elsewhere; this covers the assets that ship to every consumer or
act as starter files: shared tools, starter workflows, the integration template and the version env.
A hit here means a consumer inherits a retired runtime default, label or required-job rule.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RETIRED = re.compile(r"(?<![\d.])3\.12(?!\d)|\bpy312\b|\"3-12\"|\bcore312\b")

SCANNED = sorted(
    {
        *ROOT.glob("tools/*.py"),
        *ROOT.glob("templates/*/tools/*.py"),
        *ROOT.glob("templates/*.yml"),
        *ROOT.glob("templates/integration-repo/.github/workflows/*.yml"),
        *ROOT.glob("templates/integration-repo/pyproject.toml"),
        *ROOT.glob("templates/consumer-repo/.github/workflows/ci-python-versions.env"),
        *ROOT.glob(".github/workflows/ci-python-versions.env"),
        ROOT / "scripts" / "check_test_dependencies.sh",
    }
)


def _hits(text: str) -> list[str]:
    return [
        f"{number}: {line.strip()}"
        for number, line in enumerate(text.splitlines(), start=1)
        if RETIRED.search(line)
    ]


def test_scan_covers_the_shared_assets() -> None:
    names = {path.name for path in SCANNED}
    assert {"post_ci_summary.py", "resolve_mypy_pin.py", "ci-basic.yml"} <= names


@pytest.mark.parametrize("asset", SCANNED, ids=lambda path: str(path.relative_to(ROOT)))
def test_shared_asset_carries_no_retired_python(asset: Path) -> None:
    assert _hits(asset.read_text()) == []


def test_scan_detects_each_retired_form() -> None:
    for sample in ('python-version: "3.12"', "target = py312", 'x = ["3-12"]', 'key = "core312"'):
        assert _hits(sample), sample
    assert _hits('python-versions: \'["3.13", "3.14"]\'') == []
    assert _hits("version 13.12.1") == []
