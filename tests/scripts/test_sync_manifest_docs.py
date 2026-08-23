from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / ".github" / "sync-manifest.yml"


def test_manifest_issue_citations_are_explicitly_stateful() -> None:
    """Manifest citations name whether the referenced issue is open or resolved."""
    offenders = [
        line.strip()
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if re.findall(r"#\d+", line)
        and not re.search(r"\b(?:open|resolved):\s*(?:issue\s*)?#\d+", line)
    ]
    assert offenders == []


def test_manifest_issue_references_are_open() -> None:
    """Live guard for manifest citations explicitly marked as open."""
    if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        pytest.skip("GH_TOKEN or GITHUB_TOKEN is required to verify manifest issue references")

    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if "open:" not in line:
            continue
        for issue_number in re.findall(r"#(\d+)", line):
            result = subprocess.run(
                [
                    "gh",
                    "issue",
                    "view",
                    issue_number,
                    "--repo",
                    "stranske/Workflows",
                    "--json",
                    "state",
                    "--jq",
                    ".state",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            assert (
                result.stdout.strip() == "OPEN"
            ), f"manifest references closed issue #{issue_number}: {line.strip()}"
