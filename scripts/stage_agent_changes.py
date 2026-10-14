#!/usr/bin/env python3
"""Stage agent work without runtime artifacts; preserve existing staged source blobs."""

from __future__ import annotations

import fnmatch
import os
import subprocess

# Root-level runner outputs only: docs/evidence and other intentional proof remain eligible.
ARTIFACT_PATTERNS = tuple(
    f"{agent}-{kind}{suffix}"
    for agent in ("codex", "claude", "cursor", "gemini")
    for kind, suffix in (
        ("output", "*.md"),
        ("prompt", "*.md"),
        ("session", "*.log"),
        ("session", "*.jsonl"),
        ("analysis", "*.json"),
    )
) + (
    ".coverage",
    ".coverage.*",
    "coverage.xml",
    "pr_body.md",
    "autofix_report_enriched.json",
    "poetry.lock",
)
ARTIFACT_DIRECTORIES = {
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
}
ROOT_CHECKOUTS = {".workflows-lib", ".workflows-actions", ".reference", "coverage", "htmlcov"}


def is_artifact(path: str) -> bool:
    parts = path.split("/")
    return (
        parts[0] in ROOT_CHECKOUTS
        or any(part in ARTIFACT_DIRECTORIES for part in parts)
        or (len(parts) == 1 and any(fnmatch.fnmatchcase(path, p) for p in ARTIFACT_PATTERNS))
    )


def git(*args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *args],
        input=data,
        stdout=subprocess.PIPE,
        check=True,
        env={**os.environ, "GIT_LITERAL_PATHSPECS": "1"},
    ).stdout


def paths(*args: str) -> set[str]:
    return {os.fsdecode(p) for p in git(*args).split(b"\0") if p}


def update_index(command: tuple[str, ...], names: set[str]) -> None:
    if names:
        git(
            *command,
            "--pathspec-from-file=-",
            "--pathspec-file-nul",
            data=b"".join(os.fsencode(p) + b"\0" for p in sorted(names)),
        )


def main() -> None:
    os.chdir(os.fsdecode(git("rev-parse", "--show-toplevel")).strip())
    staged = paths("diff", "--cached", "--no-renames", "--name-only", "-z")
    # Remove even previously staged junk, without changing or deleting working files.
    update_index(("restore", "--staged"), {p for p in staged if is_artifact(p)})
    candidates = paths("diff", "--no-renames", "--name-only", "-z") | paths(
        "ls-files", "--others", "--exclude-standard", "-z"
    )
    update_index(("add", "-A"), {p for p in candidates - staged if not is_artifact(p)})


if __name__ == "__main__":
    main()
