from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / ".github" / "sync-manifest.yml"
ISSUE_REFERENCE = re.compile(r"#(?P<number>\d+)")
ISSUE_STATE_PAIR = re.compile(
    r"\b(?P<state>open|resolved):\s*(?:issue\s*)?#(?P<number>\d+)",
    re.IGNORECASE,
)


def _issue_state_pairs(line: str) -> list[tuple[str, str]]:
    return [
        (match.group("state").lower(), match.group("number"))
        for match in ISSUE_STATE_PAIR.finditer(line)
    ]


def _unpaired_issue_references(line: str) -> list[str]:
    residue = ISSUE_STATE_PAIR.sub("", line)
    return [match.group(0) for match in ISSUE_REFERENCE.finditer(residue)]


def test_manifest_issue_citations_are_explicitly_stateful() -> None:
    """Manifest citations name whether the referenced issue is open or resolved."""
    offenders = [
        line.strip()
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if _unpaired_issue_references(line)
    ]
    assert offenders == []


def test_issue_state_parser_associates_each_citation() -> None:
    line = "open: #2158; resolved: issue #2157"

    assert _issue_state_pairs(line) == [("open", "2158"), ("resolved", "2157")]
    assert _unpaired_issue_references(line) == []
    assert _unpaired_issue_references("open: #2158; also #2157") == ["#2157"]


def test_manifest_issue_references_are_open() -> None:
    """Live guard for manifest citations explicitly marked as open."""
    if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        pytest.skip("GH_TOKEN or GITHUB_TOKEN is required to verify manifest issue references")

    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        for state, issue_number in _issue_state_pairs(line):
            if state != "open":
                continue
            try:
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
                    timeout=15,
                )
            except subprocess.TimeoutExpired:
                pytest.fail(
                    f"timed out checking manifest issue #{issue_number}: {line.strip()}",
                    pytrace=False,
                )
            assert (
                result.stdout.strip() == "OPEN"
            ), f"manifest references closed issue #{issue_number}: {line.strip()}"
