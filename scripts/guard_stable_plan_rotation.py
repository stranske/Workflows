#!/usr/bin/env python3
"""Reject source-delta rotations that drop an outstanding stable PR's files."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)


def _blob_oid(repo: Path, ref: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}:{path}"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _selected(path: str, targets: set[str]) -> bool:
    return any(path == target or path.startswith(f"{target}/") for target in targets)


def uncovered_pending_paths(
    repo: Path,
    *,
    old_base: str,
    old_head: str,
    new_base: str,
    selected_targets: list[str],
) -> list[str]:
    """Find prior PR changes absent from both the new plan and consumer base."""
    for ref in (old_base, old_head, new_base):
        _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    changed = _git(repo, "diff", "--name-only", "--no-renames", "-z", old_base, old_head)
    targets = {target.rstrip("/") for target in selected_targets if target.strip()}
    paths = [
        path.decode("utf-8", errors="surrogateescape")
        for path in changed.stdout.split(b"\0")
        if path
    ]
    return sorted(
        path
        for path in paths
        if not _selected(path, targets)
        and _blob_oid(repo, old_head, path) != _blob_oid(repo, new_base, path)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--old-base", required=True)
    parser.add_argument("--old-head", required=True)
    parser.add_argument("--new-base", required=True)
    parser.add_argument("--selected-targets-file", type=Path, required=True)
    args = parser.parse_args(argv)
    targets = args.selected_targets_file.read_text(encoding="utf-8").splitlines()
    uncovered = uncovered_pending_paths(
        args.repo,
        old_base=args.old_base,
        old_head=args.old_head,
        new_base=args.new_base,
        selected_targets=targets,
    )
    if uncovered:
        print(
            "source_delta_drops_unmerged_targets: "
            + ", ".join(uncovered)
            + "; rerun Maint 68 with delivery_scope=full",
            file=sys.stderr,
        )
        return 1
    print("Source-delta rotation preserves every outstanding stable-PR path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
