#!/usr/bin/env python3
"""Fetch latest versions from PyPI and update autofix-versions.env.

This script queries PyPI for the latest stable versions of all dev tools
in the autofix-versions.env file and updates them.

CRITICAL: This script ensures we never ship outdated versions to consumer repos
by fetching the actual current versions from the authoritative source (PyPI).

Usage:
    python scripts/update_versions_from_pypi.py --check    # Show what would be updated
    python scripts/update_versions_from_pypi.py --apply    # Update autofix-versions.env
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import NamedTuple

# Path to the version pins file
PIN_FILE = Path(".github/workflows/autofix-versions.env")

# Map env keys to PyPI package names
# This is the authoritative mapping for all synced dev tools
PACKAGE_MAPPING: dict[str, str] = {
    "BLACK_VERSION": "black",
    "RUFF_VERSION": "ruff",
    "ISORT_VERSION": "isort",
    "DOCFORMATTER_VERSION": "docformatter",
    "MYPY_VERSION": "mypy",
    "PYTEST_VERSION": "pytest",
    "PYTEST_COV_VERSION": "pytest-cov",
    "PYTEST_XDIST_VERSION": "pytest-xdist",
    "COVERAGE_VERSION": "coverage",
}


class VersionInfo(NamedTuple):
    """Information about a package version."""

    current: str
    latest: str
    is_outdated: bool


def _is_prerelease(version: str) -> bool:
    return re.search(r"(a|b|rc|dev|alpha|beta)\d*$", version, re.IGNORECASE) is not None


def _is_yanked(version: str, releases: dict[str, list[dict[str, object]]]) -> bool:
    files = releases.get(version, [])
    return bool(files) and all(f.get("yanked", False) for f in files)


def get_latest_pypi_version(package_name: str) -> str | None:
    """Fetch the latest stable version from PyPI.

    This queries the PyPI JSON API and returns the latest non-prerelease version.
    Falls back to the latest release if all releases are prereleases.
    """
    url = f"https://pypi.org/pypi/{package_name}/json"
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                latest: str | None = data.get("info", {}).get("version")
                releases: dict[str, list[dict[str, object]]] = data.get("releases", {})

                if latest and not _is_prerelease(latest) and not _is_yanked(latest, releases):
                    return latest

                # Fallback: find the latest from releases
                if releases:
                    # Filter out prereleases and yanked versions
                    stable_versions: list[str] = []
                    for ver, files in releases.items():
                        # Skip if all files are yanked
                        if files and all(f.get("yanked", False) for f in files):
                            continue
                        # Skip prereleases (contains a, b, rc, dev, etc.)
                        if _is_prerelease(ver):
                            continue
                        stable_versions.append(ver)

                    if stable_versions:
                        # Sort by version tuple
                        stable_versions.sort(key=_version_tuple, reverse=True)
                        return stable_versions[0]

                return None
        except Exception as e:
            last_error = e
            if attempt < 2:
                # Brief backoff to tolerate transient network issues.
                time.sleep(0.5 * (attempt + 1))
                continue
            break

    print(f"  ⚠️  Could not fetch {package_name} from PyPI: {last_error}", file=sys.stderr)
    return None


def _version_tuple(version: str) -> tuple[int, ...]:
    """Convert version string to tuple for comparison."""
    # Handle versions like "1.2.3rc1" by stripping pre-release suffix
    clean = re.match(r"(\d+(?:\.\d+)*)", version)
    if clean:
        return tuple(int(x) for x in clean.group(1).split("."))
    return (0,)


def _is_outdated(current: str, latest: str) -> bool:
    """Return True when the current version is older than the latest version."""
    return _version_tuple(current) < _version_tuple(latest)


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse the autofix-versions.env file into a dict of key=value pairs."""
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    return values


def update_env_file(path: Path, updates: dict[str, str]) -> None:
    """Update specific values in the env file while preserving comments and order."""
    if not path.exists():
        raise FileNotFoundError(f"Pin file not found: {path}")

    lines = path.read_text(encoding="utf-8").splitlines()
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        if "=" in stripped:
            key, _ = stripped.split("=", 1)
            key = key.strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def check_versions(pin_file: Path) -> dict[str, VersionInfo]:
    """Check all versions against PyPI and return comparison info."""
    current_pins = parse_env_file(pin_file)
    results: dict[str, VersionInfo] = {}

    for env_key, package_name in PACKAGE_MAPPING.items():
        current_version = current_pins.get(env_key, "")
        if not current_version:
            print(f"  ⚠️  {env_key} not found in pin file")
            continue

        print(f"  Checking {package_name}...", end=" ", flush=True)
        latest_version = get_latest_pypi_version(package_name)

        if latest_version is None:
            print("failed to fetch")
            continue

        is_outdated = _is_outdated(current_version, latest_version)
        if is_outdated:
            status = "OUTDATED"
        elif _version_tuple(current_version) > _version_tuple(latest_version):
            status = "AHEAD"
        else:
            status = "OK"
        print(f"{current_version} -> {latest_version} [{status}]")

        results[env_key] = VersionInfo(
            current=current_version,
            latest=latest_version,
            is_outdated=is_outdated,
        )

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Update autofix-versions.env with latest versions from PyPI"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check for outdated versions without updating",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Update autofix-versions.env with latest versions",
    )
    parser.add_argument(
        "--pin-file",
        type=Path,
        default=PIN_FILE,
        help=f"Path to pin file (default: {PIN_FILE})",
    )
    parser.add_argument(
        "--fail-on-outdated",
        action="store_true",
        help="Exit with code 1 if any version is outdated (useful for CI)",
    )

    args = parser.parse_args(argv)

    if not args.check and not args.apply:
        parser.error("Must specify either --check or --apply")

    print(f"Checking versions in {args.pin_file}...")
    results = check_versions(args.pin_file)

    outdated = {k: v for k, v in results.items() if v.is_outdated}

    if not outdated:
        print("\n✅ All versions are up to date!")
        return 0

    print(f"\n⚠️  Found {len(outdated)} outdated version(s):")
    for env_key, info in outdated.items():
        pkg = PACKAGE_MAPPING[env_key]
        print(f"  {pkg}: {info.current} -> {info.latest}")

    if args.apply:
        updates = {k: v.latest for k, v in outdated.items()}
        update_env_file(args.pin_file, updates)
        print(f"\n✅ Updated {len(updates)} version(s) in {args.pin_file}")
        return 0

    if args.fail_on_outdated:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
