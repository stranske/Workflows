#!/usr/bin/env python3
"""Provision test dependencies from pyproject.toml before collecting the suite."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPORT_CHECK = (
    "import defusedxml; from mypy import api; import pytest; print('Validation imports OK')"
)


def provision(environment: Path, *, system_site_packages: bool = False) -> Path:
    """Install the project's runtime and dev requirements, then fail on missing imports."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    requirement = project["requires-python"]
    floor = re.fullmatch(r">=(\d+)\.(\d+)", requirement)
    if floor is None:
        raise ValueError(f"Unsupported requires-python constraint: {requirement}")
    if sys.version_info[:2] < tuple(map(int, floor.groups())):
        raise ValueError(
            f"Python {requirement} required; run this script with a supported interpreter"
        )

    environment = environment.resolve()
    create = [sys.executable, "-m", "venv"]
    if system_site_packages:
        create.append("--system-site-packages")
    subprocess.run([*create, str(environment)], check=True)
    python = environment / "bin" / "python3"
    # This automation repo declares packages=[]; only its declared dependencies
    # are needed. Avoid an editable build (and writes into the source checkout).
    dependencies = [*project["dependencies"], *project["optional-dependencies"]["dev"]]
    subprocess.run([str(python), "-m", "pip", "install", *dependencies], check=True)
    subprocess.run([str(python), "-c", IMPORT_CHECK], check=True)
    return python


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", type=Path, help="Virtual environment directory")
    parser.add_argument(
        "--system-site-packages",
        action="store_true",
        help="Reuse preinstalled runner packages; pip still resolves every declared dependency",
    )
    args = parser.parse_args()
    try:
        python = provision(args.environment, system_site_packages=args.system_site_packages)
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"Validation environment setup failed: {exc}", file=sys.stderr)
        return 1
    print(f"Environment ready: {python}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
