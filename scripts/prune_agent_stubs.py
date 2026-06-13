"""Garbage-collect per-issue agent bootstrap stubs in agents/.

Only removes ``agents/<agent>-<N>.md`` stubs whose issue ``#N`` is closed.
Stubs for open issues (or names that don't match the pattern) are left alone.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# Pattern: lowercase-start, alphanum/dash body, trailing digits, .md extension.
_STUB_RE = re.compile(r"^[a-z][a-z0-9-]*-(\d+)\.md$")

AGENTS_DIR = Path("agents")


def select_prunable(
    stub_names: list[str],
    closed_issue_numbers: set[int],
) -> list[str]:
    """Return the subset of *stub_names* whose issue number is in *closed_issue_numbers*.

    Names that do not match ``^[a-z][a-z0-9-]*-\\d+\\.md$`` are silently ignored.
    The function is pure — no filesystem or network access.

    Args:
        stub_names: Candidate filenames (basenames only, e.g. ``auto-pilot-755.md``).
        closed_issue_numbers: Set of issue numbers known to be closed.

    Returns:
        Sorted list of stub names that should be pruned.
    """
    prunable: list[str] = []
    for name in stub_names:
        m = _STUB_RE.match(name)
        if m and int(m.group(1)) in closed_issue_numbers:
            prunable.append(name)
    return sorted(prunable)


def _fetch_closed_issue_numbers(repo: str) -> set[int]:
    """Query GitHub for all closed issue numbers in *repo* via ``gh``."""
    result = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "closed",
            "--limit",
            "10000",
            "--json",
            "number",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    items: list[dict[str, int]] = json.loads(result.stdout)
    return {item["number"] for item in items}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Prune closed-issue agent stubs from agents/")
    parser.add_argument(
        "--repo",
        default="stranske/Workflows",
        help="GitHub repo slug (default: stranske/Workflows)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be deleted without deleting anything",
    )
    args = parser.parse_args(argv)

    if not AGENTS_DIR.is_dir():
        print(f"agents/ directory not found (cwd={Path.cwd()})", file=sys.stderr)
        return 1

    stub_names = [p.name for p in AGENTS_DIR.iterdir() if p.is_file()]
    closed = _fetch_closed_issue_numbers(args.repo)
    to_prune = select_prunable(stub_names, closed)

    if not to_prune:
        print("Nothing to prune.")
        return 0

    for name in to_prune:
        path = AGENTS_DIR / name
        if args.dry_run:
            print(f"[dry-run] would delete {path}")
        else:
            path.unlink()
            print(f"Deleted {path}")

    print(f"\n{'Would delete' if args.dry_run else 'Deleted'} {len(to_prune)} stub(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
