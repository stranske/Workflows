#!/usr/bin/env python3
"""Update langchain dependencies to latest stable versions across repos."""
import json
import re
import subprocess
import sys
from pathlib import Path


def get_latest_pypi_version(package: str) -> str:
    """Fetch latest version from PyPI."""
    result = subprocess.run(
        ["curl", "-s", f"https://pypi.org/pypi/{package}/json"],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    return data["info"]["version"]


def get_major_minor(version: str) -> tuple[int, int]:
    """Extract major.minor from version string."""
    match = re.match(r"^(\d+)\.(\d+)", version)
    if not match:
        raise ValueError(f"Cannot parse version: {version}")
    return int(match.group(1)), int(match.group(2))


def main() -> int:
    packages = {
        "langchain": None,
        "langchain-core": None,
        "langchain-community": None,
        "langchain-openai": None,
    }
    
    print("Fetching latest versions from PyPI...")
    for package in packages:
        try:
            version = get_latest_pypi_version(package)
            packages[package] = version
            major, minor = get_major_minor(version)
            print(f"  {package}: {version} (^{major}.{minor})")
        except Exception as e:
            print(f"  ERROR fetching {package}: {e}", file=sys.stderr)
            return 1
    
    print("\nRecommended pyproject.toml entries:")
    print("langchain = [")
    for package, version in packages.items():
        major, minor = get_major_minor(version)
        # Pin to major.minor range for stability
        print(f'    "{package}>={major}.{minor},<{major}.{minor+1}",')
    print("]")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
