"""Expose dependency metadata to pip's editable resolver without installing code.

The test creates a minimal project with the historical dev-tool requirements.
This backend exercises PEP 660 metadata preparation, not either product's build.
"""

from __future__ import annotations

import tomllib
from pathlib import Path


def prepare_metadata_for_build_editable(
    metadata_directory: str, config_settings: dict | None = None
) -> str:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    name = project["name"]
    version = project["version"]
    dist_info = f"{name.replace('-', '_')}-{version}.dist-info"
    destination = Path(metadata_directory) / dist_info
    destination.mkdir()
    requirements = "".join(
        f'Requires-Dist: {requirement}; extra == "dev"\n'
        for requirement in project["optional-dependencies"]["dev"]
    )
    (destination / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
        f"Provides-Extra: dev\n{requirements}",
        encoding="utf-8",
    )
    return dist_info


def build_editable(
    wheel_directory: str,
    config_settings: dict | None = None,
    metadata_directory: str | None = None,
) -> str:
    raise AssertionError("The bounded resolver test must only prepare metadata")
