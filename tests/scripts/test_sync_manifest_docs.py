from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / ".github" / "sync-manifest.yml"


def test_manifest_issue_references_are_open() -> None:
    """A manifest citation must resolve to an open issue or be explicitly resolved."""
    if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        pytest.skip("GH_TOKEN or GITHUB_TOKEN is required to verify manifest issue references")

    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if "resolved:" in line:
            continue
        for issue_number in re.findall(r"#(\d+)", line):
            result = subprocess.run(
                ["gh", "issue", "view", issue_number, "--repo", "stranske/Workflows", "--json", "state", "--jq", ".state"],
                check=True,
                capture_output=True,
                text=True,
            )
            assert result.stdout.strip() == "OPEN", f"manifest references closed issue #{issue_number}: {line.strip()}"
