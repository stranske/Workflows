#!/usr/bin/env python3
"""Create verifier labels across consumer repositories via gh CLI."""

from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path

LABELS = (
    {
        "name": "verify:checkbox",
        "color": "0E8A16",
        "description": "Runs verifier checkbox mode after merge",
    },
    {
        "name": "verify:evaluate",
        "color": "FBCA04",
        "description": "Runs verifier evaluation mode after merge",
    },
    {
        "name": "verify:compare",
        "color": "1D76DB",
        "description": "Runs verifier comparison mode after merge",
    },
)


def _parse_repos_from_workflow(path: Path) -> list[str]:
    if not path.exists():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    start_index = None
    for index, line in enumerate(lines):
        if line.strip().startswith("REGISTERED_CONSUMER_REPOS:"):
            start_index = index
            break

    if start_index is None:
        return []

    repos: list[str] = []
    for line in lines[start_index + 1 :]:
        if not line.startswith(" "):
            break
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        repos.append(entry)

    return repos


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_repo_list(repos: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for repo in repos:
        if repo in seen:
            continue
        seen.add(repo)
        ordered.append(repo)
    return ordered


def _build_command(repo: str, label: dict[str, str]) -> list[str]:
    return [
        "gh",
        "label",
        "create",
        label["name"],
        "--repo",
        repo,
        "--color",
        label["color"],
        "--description",
        label["description"],
        "--force",
    ]


def _format_command(cmd: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create verifier labels via gh CLI.")
    parser.add_argument(
        "--repos",
        help="Comma-separated list of repos (overrides --repos-file).",
    )
    parser.add_argument(
        "--repos-file",
        default=".github/workflows/maint-68-sync-consumer-repos.yml",
        help="Workflow file containing REGISTERED_CONSUMER_REPOS.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Repo to exclude (repeatable).",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Only run for these repos (repeatable).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run gh commands (default: dry run).",
    )

    args = parser.parse_args()

    repos = _split_csv(args.repos)
    if not repos:
        repos = _parse_repos_from_workflow(Path(args.repos_file))

    repos = _normalize_repo_list(repos)
    if args.only:
        allowlist = {repo.strip() for repo in args.only if repo.strip()}
        repos = [repo for repo in repos if repo in allowlist]

    if args.exclude:
        blocklist = {repo.strip() for repo in args.exclude if repo.strip()}
        repos = [repo for repo in repos if repo not in blocklist]

    if not repos:
        raise SystemExit("No repos found to process.")

    for repo in repos:
        for label in LABELS:
            cmd = _build_command(repo, label)
            if args.execute:
                subprocess.run(cmd, check=True)
            else:
                print(_format_command(cmd))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
