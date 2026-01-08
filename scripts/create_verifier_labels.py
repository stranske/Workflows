#!/usr/bin/env python3
"""Create verifier labels across consumer repositories via gh CLI."""

from __future__ import annotations

import argparse
import json
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
    {
        "name": "verify:create-issue",
        "color": "D93F0B",
        "description": "Creates follow-up issue from verification feedback",
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


def _filter_labels(labels: tuple[dict[str, str], ...], names: list[str]) -> list[dict[str, str]]:
    if not names:
        return list(labels)

    name_set = {name.strip() for name in names if name.strip()}
    filtered = [label for label in labels if label["name"] in name_set]
    missing = name_set.difference({label["name"] for label in filtered})
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise SystemExit(f"Unknown label name(s): {missing_list}")
    return filtered


def _validate_repo_count(repos: list[str], expected: int | None) -> None:
    if expected is None:
        return
    if len(repos) != expected:
        raise SystemExit(f"Expected {expected} repos, found {len(repos)}.")


def _extract_label_names(payload: str) -> set[str]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Unable to parse label list JSON: {exc}") from exc
    if not isinstance(data, list):
        raise SystemExit("Unexpected label list payload (expected a list).")
    names = {
        item.get("name", "").strip()
        for item in data
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    return {name for name in names if name}


def _find_missing_labels(existing: set[str], labels: list[dict[str, str]]) -> list[str]:
    return [label["name"] for label in labels if label["name"] not in existing]


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


def _build_list_command(repo: str) -> list[str]:
    return [
        "gh",
        "label",
        "list",
        "--repo",
        repo,
        "--json",
        "name",
        "--limit",
        "500",
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
        "--labels",
        help="Comma-separated list of label names to create (default: all).",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Only run for these repos (repeatable).",
    )
    parser.add_argument(
        "--expect-count",
        type=int,
        help="Require a specific number of repos before proceeding.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run gh label create commands (default: dry run).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="List missing labels per repo and exit nonzero if any are missing.",
    )

    args = parser.parse_args()

    if args.execute and args.check:
        raise SystemExit("Choose either --execute or --check, not both.")

    repos = _split_csv(args.repos)
    if not repos:
        repos = _parse_repos_from_workflow(Path(args.repos_file))

    repos = _normalize_repo_list(repos)
    labels = _filter_labels(LABELS, _split_csv(args.labels))
    if args.only:
        allowlist = {repo.strip() for repo in args.only if repo.strip()}
        repos = [repo for repo in repos if repo in allowlist]

    if args.exclude:
        blocklist = {repo.strip() for repo in args.exclude if repo.strip()}
        repos = [repo for repo in repos if repo not in blocklist]

    _validate_repo_count(repos, args.expect_count)

    if not repos:
        raise SystemExit("No repos found to process.")

    if args.check:
        missing_any = False
        for repo in repos:
            cmd = _build_list_command(repo)
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            existing = _extract_label_names(result.stdout)
            missing = _find_missing_labels(existing, labels)
            if missing:
                missing_any = True
                print(f"{repo}: missing {', '.join(missing)}")
            else:
                print(f"{repo}: ok")
        return 1 if missing_any else 0

    for repo in repos:
        for label in labels:
            cmd = _build_command(repo, label)
            if args.execute:
                subprocess.run(cmd, check=True)
            else:
                print(_format_command(cmd))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
