#!/usr/bin/env python3
"""Create GitHub issues from the approved weekly repo-review queue.

The script is intentionally explicit: dry-run is the default, and `--apply`
is required before it writes to GitHub. Creation is idempotent against open
issues with the exact same title in the target repo.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from scripts.repo_review_issue_quality import (
        issue_body_quality_errors,
        review_evidence_trace_errors,
    )
except ModuleNotFoundError:  # pragma: no cover - supports direct script execution.
    from repo_review_issue_quality import (  # type: ignore[no-redef]
        issue_body_quality_errors,
        review_evidence_trace_errors,
    )

LABELS = {
    "repo-review-approved": {
        "color": "5319e7",
        "description": "Approved by weekly design-vs-implementation repo review",
    },
    "repo-review-meta-audit": {
        "color": "8957a0",
        "description": "Audit-scope candidate from weekly repo review (produce a report + follow-ups, not a single fix)",
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
SEMANTIC_DUPLICATE_LABEL = "repo-review-approved"
SEMANTIC_DUPLICATE_THRESHOLD = 0.20
SEMANTIC_DUPLICATE_MARGIN = 0.08
SEMANTIC_DUPLICATE_STOPWORDS = {
    "acceptance",
    "add",
    "after",
    "and",
    "are",
    "before",
    "behavior",
    "code",
    "complete",
    "coverage",
    "criteria",
    "current",
    "database",
    "design",
    "docs",
    "documentation",
    "document",
    "existing",
    "file",
    "files",
    "finish",
    "fix",
    "for",
    "from",
    "goals",
    "implementation",
    "implement",
    "into",
    "issue",
    "issues",
    "local",
    "manager",
    "mode",
    "non",
    "notes",
    "path",
    "paths",
    "readiness",
    "relevant",
    "repo",
    "review",
    "reviewed",
    "scope",
    "should",
    "tasks",
    "test",
    "tests",
    "than",
    "that",
    "the",
    "this",
    "use",
    "using",
    "why",
    "with",
    "without",
}


def run_command(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def run_command_with_retry(
    args: list[str], *, attempts: int = 2, label: str = ""
) -> subprocess.CompletedProcess[str]:
    """Run `gh` with one retry on non-zero exit. The pilot upload hit two
    transient subprocess failures (one on `gh issue list` for a repo with
    1000+ issues, one on `gh issue create`) that succeeded on retry. We
    don't want the entire weekly upload to crash on a one-off network or
    rate-limit blip — retry once, then surface the failure if it persists.
    """
    last_result: subprocess.CompletedProcess[str] | None = None
    for attempt in range(1, attempts + 1):
        result = subprocess.run(args, check=False, capture_output=True, text=True)
        if result.returncode == 0:
            return result
        last_result = result
        if attempt < attempts:
            print(
                f"[upload] {label or args[1] if len(args) > 1 else 'gh'} attempt {attempt}/{attempts} "
                f"failed (rc={result.returncode}); retrying. stderr: {result.stderr.strip()[:200]}",
                file=sys.stderr,
            )
    assert last_result is not None
    raise subprocess.CalledProcessError(
        last_result.returncode,
        last_result.args,
        output=last_result.stdout,
        stderr=last_result.stderr,
    )


def gh_command(prefix: list[str], *args: str) -> list[str]:
    return [*prefix, *args]


def load_queue(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    issues = data.get("issues", [])
    if not isinstance(issues, list):
        raise ValueError(f"{path} does not contain an issues list")
    loaded = [issue for issue in issues if isinstance(issue, dict)]
    validate_issue_queue(loaded)
    return loaded


def validate_issue_queue(issues: list[dict[str, Any]]) -> None:
    failures: list[str] = []
    for index, issue in enumerate(issues, start=1):
        repo = str(issue.get("repo") or "<missing repo>")
        title = str(issue.get("title") or "<missing title>")
        body = str(issue.get("body") or "")
        if not repo or repo == "<missing repo>":
            failures.append(f"issue {index} is missing repo")
        if not title or title == "<missing title>":
            failures.append(f"issue {index} is missing title")
        for error in issue_body_quality_errors(body):
            failures.append(f"{repo} :: {title}: {error}")
        for error in review_evidence_trace_errors(issue.get("review_evidence_trace")):
            failures.append(f"{repo} :: {title}: {error}")
    if failures:
        joined = "\n- ".join(failures)
        raise ValueError(f"approved issue queue failed quality validation:\n- {joined}")


def fetch_open_issues(repo: str, prefix: list[str]) -> list[dict[str, Any]]:
    result = run_command_with_retry(
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
        label=f"issue-list[{repo}]",
    )
    return json.loads(result.stdout or "[]")


def issue_labels(issue: dict[str, Any]) -> set[str]:
    return {str(label.get("name")) for label in issue.get("labels", []) if isinstance(label, dict)}


def duplicate_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", text.lower())
        if len(token) > 2 and token not in SEMANTIC_DUPLICATE_STOPWORDS
    }


def duplicate_text(issue: dict[str, Any]) -> str:
    trace = issue.get("review_evidence_trace") if isinstance(issue, dict) else None
    trace_text = ""
    if isinstance(trace, dict):
        trace_text = " ".join(
            str(value)
            for key in ("gap", "current_state", "required_change")
            for value in [trace.get(key)]
            if value
        )
    return "\n".join(
        [
            str(issue.get("title") or ""),
            str(issue.get("body") or ""),
            trace_text,
        ]
    )


def duplicate_similarity(candidate: dict[str, Any], existing: dict[str, Any]) -> float:
    candidate_tokens = duplicate_tokens(duplicate_text(candidate))
    existing_tokens = duplicate_tokens(duplicate_text(existing))
    if not candidate_tokens or not existing_tokens:
        return 0.0
    return len(candidate_tokens & existing_tokens) / len(candidate_tokens | existing_tokens)


def find_semantic_duplicate(
    candidate: dict[str, Any], open_issues: list[dict[str, Any]]
) -> dict[str, Any] | None:
    scored: list[tuple[float, dict[str, Any]]] = []
    for issue in open_issues:
        if SEMANTIC_DUPLICATE_LABEL not in issue_labels(issue):
            continue
        scored.append((duplicate_similarity(candidate, issue), issue))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_issue = scored[0]
    next_score = scored[1][0] if len(scored) > 1 else 0.0
    if (
        best_score >= SEMANTIC_DUPLICATE_THRESHOLD
        and best_score - next_score >= SEMANTIC_DUPLICATE_MARGIN
    ):
        return best_issue
    return None


DEFAULT_LABEL_COLOR = "ededed"
DEFAULT_LABEL_DESCRIPTION = "Auto-created by repo-review upload helper."


def ensure_labels(repo: str, labels: list[str], prefix: list[str]) -> None:
    """Create each label on the target repo if missing.

    For labels in the `LABELS` registry, use the canonical color/description.
    For unknown labels (e.g. a future audit-scope label not yet promoted to
    LABELS), create them with neutral defaults rather than crashing — we'd
    rather have a less-pretty label than block 18 issue uploads on a
    schema-registry mismatch. `gh label create` is a no-op if the label
    already exists, so this is idempotent.
    """
    for label in labels:
        config = LABELS.get(
            label,
            {
                "color": DEFAULT_LABEL_COLOR,
                "description": DEFAULT_LABEL_DESCRIPTION,
            },
        )
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
        result = run_command_with_retry(
            [*args, "--body-file", body_file.name],
            label=f"issue-create[{issue['repo']}]",
        )
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
    validate_issue_queue(issues)
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
            existing = open_by_title.get(title) or find_semantic_duplicate(issue, open_issues)
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
        help="Path to approved-issue-queue.json (default: the path the "
        "coordinator's queue-builder writes)",
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
    try:
        issues = load_queue(args.queue)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
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
