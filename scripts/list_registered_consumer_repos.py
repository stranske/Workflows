#!/usr/bin/env python3
"""
Utility script to list the registered consumer repos from maint-68-sync-consumer-repos.yml.

Usage:
  python scripts/list_registered_consumer_repos.py [--manifest PATH] [--separator ',']
"""

from __future__ import annotations

import argparse
from pathlib import Path

OWNER_EXCLUDED_REPOSITORIES = frozenset({"stranske/collab-admin"})


def is_owner_excluded(repo: str) -> bool:
    return repo.strip().casefold() in OWNER_EXCLUDED_REPOSITORIES


def extract_repos(manifest: Path) -> list[str]:
    lines = manifest.read_text(encoding="utf-8").splitlines()
    repos: list[str] = []
    in_block = False

    for line in lines:
        stripped = line.strip()
        if not in_block:
            starts_marker = stripped.startswith("REGISTERED_CONSUMER_REPOS:")
            ends_block = line.rstrip().endswith("|")
            if starts_marker and ends_block:
                in_block = True
            continue

        if line and not line.startswith(" "):
            break

        value = stripped
        if value and not is_owner_excluded(value):
            repos.append(value)

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
