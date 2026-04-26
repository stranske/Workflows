#!/usr/bin/env python3
"""Create GitHub issues from the approved weekly repo-review queue.

The script is intentionally explicit: dry-run is the default, and `--apply`
is required before it writes to GitHub. Creation is idempotent against open
issues with the exact same title in the target repo.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any

LABELS = {
    "repo-review-approved": {
        "color": "5319e7",
        "description": "Approved by weekly design-vs-implementation repo review",
    },
    "priority:high": {
        "color": "b60205",
        "description": "High-priority weekly repo-review work",
    },
    "priority:normal": {
        "color": "fbca04",
        "description": "Normal-priority weekly repo-review work",
    },
    "priority:low": {
        "color": "0e8a16",
        "description": "Low-priority weekly repo-review work",
    },
}


def run_command(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def gh_command(prefix: list[str], *args: str) -> list[str]:
    return [*prefix, *args]


def load_queue(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    issues = data.get("issues", [])
    if not isinstance(issues, list):
        raise ValueError(f"{path} does not contain an issues list")
    return [issue for issue in issues if isinstance(issue, dict)]


def fetch_open_issues(repo: str, prefix: list[str]) -> list[dict[str, Any]]:
    result = run_command(
        gh_command(
            prefix,
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--limit",
            "500",
            "--json",
            "number,title,labels,url",
        ),
        check=True,
    )
    return json.loads(result.stdout or "[]")


def ensure_labels(repo: str, labels: list[str], prefix: list[str]) -> None:
    for label in labels:
        config = LABELS.get(label)
        if not config:
            continue
        run_command(
            gh_command(
                prefix,
                "label",
                "create",
                label,
                "--repo",
                repo,
                "--color",
                config["color"],
                "--description",
                config["description"],
            )
        )


def add_missing_labels(
    repo: str,
    issue_number: int,
    labels: list[str],
    existing_labels: list[dict[str, Any]],
    prefix: list[str],
) -> None:
    existing = {label.get("name") for label in existing_labels}
    missing = [label for label in labels if label not in existing]
    if not missing:
        return
    run_command(
        gh_command(
            prefix,
            "issue",
            "edit",
            str(issue_number),
            "--repo",
            repo,
            "--add-label",
            ",".join(missing),
        ),
        check=True,
    )


def create_issue(issue: dict[str, Any], prefix: list[str]) -> str:
    labels = [str(label) for label in issue.get("labels", [])]
    args = gh_command(
        prefix,
        "issue",
        "create",
        "--repo",
        str(issue["repo"]),
        "--title",
        str(issue["title"]),
    )
    for label in labels:
        args.extend(["--label", label])
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md") as body_file:
        body_file.write(str(issue["body"]))
        body_file.flush()
        result = run_command([*args, "--body-file", body_file.name], check=True)
    return result.stdout.strip()


def upload_issues(
    issues: list[dict[str, Any]],
    *,
    prefix: list[str],
    apply: bool,
    repo_filter: set[str] | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "apply": apply,
        "created": [],
        "skipped_duplicates": [],
        "would_create": [],
    }
    by_repo: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        repo = str(issue.get("repo", ""))
        if not repo:
            continue
        if repo_filter and repo not in repo_filter:
            continue
        by_repo.setdefault(repo, []).append(issue)

    for repo, repo_issues in sorted(by_repo.items()):
        open_issues = fetch_open_issues(repo, prefix)
        open_by_title = {item.get("title"): item for item in open_issues}
        labels = sorted({label for issue in repo_issues for label in issue.get("labels", [])})
        if apply:
            ensure_labels(repo, labels, prefix)
        for issue in repo_issues:
            title = str(issue["title"])
            existing = open_by_title.get(title)
            if existing:
                if apply:
                    add_missing_labels(
                        repo,
                        int(existing["number"]),
                        [str(label) for label in issue.get("labels", [])],
                        existing.get("labels", []),
                        prefix,
                    )
                summary["skipped_duplicates"].append(
                    {
                        "repo": repo,
                        "title": title,
                        "number": existing.get("number"),
                        "url": existing.get("url"),
                    }
                )
                continue
            if not apply:
                summary["would_create"].append({"repo": repo, "title": title})
                continue
            url = create_issue(issue, prefix)
            summary["created"].append({"repo": repo, "title": title, "url": url})
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--queue",
        type=Path,
        default=Path("docs/reports/repo-review/approved-issue-queue.json"),
        help="Path to approved-issue-queue.json",
    )
    parser.add_argument(
        "--gh-prefix",
        default="gh",
        help="Command prefix for GitHub CLI calls, e.g. 'gh' or 'detached-net.sh gh'",
    )
    parser.add_argument("--repo", action="append", default=[], help="Limit upload to this repo.")
    parser.add_argument("--apply", action="store_true", help="Create/edit issues on GitHub.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    issues = load_queue(args.queue)
    summary = upload_issues(
        issues,
        prefix=shlex.split(args.gh_prefix),
        apply=args.apply,
        repo_filter=set(args.repo) if args.repo else None,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
