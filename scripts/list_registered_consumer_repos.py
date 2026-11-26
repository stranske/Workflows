#!/usr/bin/env python3
"""
Utility script to list the registered consumer repos from maint-68-sync-consumer-repos.yml.

Usage:
  python scripts/list_registered_consumer_repos.py [--manifest PATH] [--separator ',']
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

OWNER_EXCLUDED_REPOSITORIES = frozenset({"stranske/collab-admin"})
_REGISTRY_HEADER = re.compile(r"^( *)REGISTERED_CONSUMER_REPOS\s*:\s*\|\s*$")


def is_owner_excluded(repo: str) -> bool:
    return repo.strip().casefold() in OWNER_EXCLUDED_REPOSITORIES


def extract_repos(manifest: Path, *, require_block: bool = False) -> list[str]:
    """Read the ordered literal registry, optionally requiring its header."""
    lines = manifest.read_text(encoding="utf-8").splitlines()
    repos: list[str] = []
    key_indent = None
    block_indent = None

    for line in lines:
        if key_indent is None:
            header = _REGISTRY_HEADER.fullmatch(line)
            if header:
                key_indent = len(header.group(1))
            continue

        value = line.strip()
        if not value:
            continue

        indent = len(line) - len(line.lstrip(" "))
        if indent <= key_indent:
            break
        if block_indent is None:
            block_indent = indent
        if indent < block_indent:
            break

        if not is_owner_excluded(value):
            repos.append(value)

    if require_block and key_indent is None:
        raise ValueError("Could not find REGISTERED_CONSUMER_REPOS: | block")
    return repos


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        default=".github/workflows/maint-68-sync-consumer-repos.yml",
        help="Path to maint-68-sync-consumer-repos.yml",
    )
    parser.add_argument(
        "--separator",
        default="\n",
        help="Separator between repo names (default: newline)",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    repos = extract_repos(manifest_path)
    print(args.separator.join(repos))


if __name__ == "__main__":
    main()
