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


def test_manifest_issue_references_are_open() -> None:
    """Every manifest issue citation names whether that issue is open or resolved.

    This is the strict check, and it is the one #3183's acceptance criterion cited by
    node id. It ran under the name `test_manifest_issue_citations_are_explicitly_stateful`
    while the name `test_manifest_issue_references_are_open` belonged to the
    network-gated probe below -- which only iterates citations marked `open:`, of which
    the manifest has ZERO (five are `resolved:`). So the cited node id resolved to a
    test that verified nothing even with a token present. The names are now swapped so
    the cited id names the check that does the work.
    """
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


def test_open_manifest_issue_citations_are_still_open() -> None:
    """Live guard for the subset of citations explicitly marked `open:`.

    NAME SAYS THE SCOPE ON PURPOSE: this iterates only `open:` citations, so when the
    manifest has none it is vacuous by construction, not broken. That is fine for a
    live probe and fatal for an acceptance criterion, which is why the strict offline
    check above now carries the cited name.
    """
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
