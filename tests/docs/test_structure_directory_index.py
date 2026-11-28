"""docs/STRUCTURE.md is the only layout map, and it lists every directory (round-2 E2).

Before 2026-11-28 three layout descriptions (README, docs/README.md, STRUCTURE.md)
disagreed with the tree: STRUCTURE missed about 15 second-level directories, the docs
index missed 15 of 23 docs/ subdirectories, and the README still described a src/ that
had changed. Now STRUCTURE's directory index must list exactly the directories that hold
tracked files at depth one and two, and the other two documents link to it.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STRUCTURE = ROOT / "docs/STRUCTURE.md"
# Per-issue record folders are listed once, as a pattern.
PATTERNS = ((re.compile(r"^evidence/issue-\d+$"), "evidence/issue-<number>"),)


def _tracked_directories() -> set[str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"}
    }
    output = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, env=env, check=True, capture_output=True
    ).stdout
    files = [path for path in output.decode("utf-8").split("\0") if path]
    dirs: set[str] = set()
    for path in files:
        parts = path.split("/")
        if len(parts) >= 2:
            dirs.add(parts[0])
        if len(parts) >= 3:
            dirs.add("/".join(parts[:2]))
    normalised = set()
    for directory in dirs:
        for pattern, replacement in PATTERNS:
            if pattern.match(directory):
                directory = replacement
        normalised.add(directory)
    return normalised


def _indexed_directories() -> set[str]:
    text = STRUCTURE.read_text(encoding="utf-8")
    section = text.split("## Directory index", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"^\| `([^`]+)/` \|", section, flags=re.MULTILINE))


def test_index_lists_exactly_the_tracked_directories() -> None:
    tracked = _tracked_directories()
    indexed = _indexed_directories()
    assert sorted(tracked - indexed) == [], "add these directories to docs/STRUCTURE.md"
    assert sorted(indexed - tracked) == [], "these indexed directories no longer exist"


def test_readme_and_docs_index_point_to_the_one_map() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docs_index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    assert "docs/STRUCTURE.md#directory-index" in readme
    assert "STRUCTURE.md#directory-index" in docs_index
    # The README no longer keeps its own directory list.
    assert "### Other Top-level Code Homes" not in readme
