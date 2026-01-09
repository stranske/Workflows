#!/usr/bin/env python3
"""Create GitHub issues for agents-dedup smoke testing."""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests

from scripts.langchain import issue_dedup

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 30


@dataclass(frozen=True)
class SourceIssue:
    number: int
    title: str
    body: str | None
    url: str | None


@dataclass(frozen=True)
class SimilarIssueRef:
    number: int | None
    url: str | None
    title: str | None


def build_issue_payload(title: str, body: str | None, labels: list[str] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"title": title}
    if body is not None:
        payload["body"] = body
    if labels:
        payload["labels"] = labels
    return payload


def format_body_with_note(body: str | None, note: str | None) -> str | None:
    if not note:
        return body
    if body:
        return f"{body}\n\n{note}"
    return note


def parse_source_issue(data: dict[str, Any]) -> SourceIssue:
    try:
        number = int(data["number"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Source issue is missing a numeric 'number'.") from exc
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValueError("Source issue is missing a title.")
    return SourceIssue(
        number=number,
        title=title,
        body=data.get("body"),
        url=data.get("html_url") or data.get("url"),
    )


def _request_json(method: str, url: str, token: str, payload: dict[str, Any] | None) -> Any:
    response = requests.request(
        method,
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        json=payload,
        timeout=DEFAULT_TIMEOUT,
    )
    if response.status_code >= 400:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise RuntimeError(f"GitHub API error {response.status_code}: {detail}")
    if response.status_code == 204:
        return None
    return response.json()


def _build_url(base_url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return base_url
    return f"{base_url}?{urlencode(params)}"


def fetch_issue(repo: str, issue_number: int, token: str) -> SourceIssue:
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}"
    data = _request_json("GET", url, token, payload=None)
    if not isinstance(data, dict):
        raise RuntimeError("GitHub API did not return a JSON object for the issue.")
    return parse_source_issue(data)


def fetch_issues(
    repo: str,
    token: str,
    *,
    labels: list[str] | None,
    page: int,
    per_page: int = 100,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"state": "open", "page": page, "per_page": per_page}
    if labels:
        params["labels"] = ",".join(labels)
    url = _build_url(f"{GITHUB_API}/repos/{repo}/issues", params)
    data = _request_json("GET", url, token, payload=None)
    if not isinstance(data, list):
        raise RuntimeError("GitHub API did not return a JSON array for issues.")
    return data


def fetch_issue_comments(repo: str, issue_number: int, token: str) -> list[dict[str, Any]]:
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments?per_page=100"
    data = _request_json("GET", url, token, payload=None)
    if not isinstance(data, list):
        raise RuntimeError("GitHub API did not return a JSON array for issue comments.")
    return data


def create_issue(
    repo: str,
    token: str,
    title: str,
    body: str | None,
    labels: list[str] | None,
) -> dict[str, Any]:
    url = f"{GITHUB_API}/repos/{repo}/issues"
    payload = build_issue_payload(title, body, labels)
    data = _request_json("POST", url, token, payload=payload)
    if not isinstance(data, dict):
        raise RuntimeError("GitHub API did not return a JSON object for the issue.")
    return data


def build_duplicate_payload(
    source_issue: SourceIssue,
    *,
    title_suffix: str,
    note: str | None,
    labels: list[str] | None,
) -> dict[str, Any]:
    body = format_body_with_note(source_issue.body, note)
    title = f"{source_issue.title}{title_suffix}"
    return build_issue_payload(title, body, labels)


def filter_issues_by_query(
    issues: list[dict[str, Any]],
    query: str | None,
) -> list[SourceIssue]:
    matches: list[SourceIssue] = []
    query_lower = query.lower() if query else None
    for entry in issues:
        if "pull_request" in entry:
            continue
        title = str(entry.get("title") or "")
        body = str(entry.get("body") or "")
        if query_lower and query_lower not in title.lower() and query_lower not in body.lower():
            continue
        try:
            matches.append(parse_source_issue(entry))
        except ValueError:
            continue
    return matches


def select_issue_by_query(
    issues: list[dict[str, Any]],
    query: str,
) -> SourceIssue | None:
    matches = filter_issues_by_query(issues, query)
    return matches[0] if matches else None


def find_source_issue(
    repo: str,
    token: str,
    *,
    query: str,
    labels: list[str] | None,
    pages: int,
) -> SourceIssue | None:
    max_pages = max(pages, 1)
    for page in range(1, max_pages + 1):
        issues = fetch_issues(repo, token, labels=labels, page=page)
        match = select_issue_by_query(issues, query)
        if match is not None:
            return match
        if not issues:
            break
    return None


def collect_matching_issues(
    repo: str,
    token: str,
    *,
    query: str | None,
    labels: list[str] | None,
    pages: int,
    limit: int | None = None,
) -> list[SourceIssue]:
    max_pages = max(pages, 1)
    matches: list[SourceIssue] = []
    for page in range(1, max_pages + 1):
        issues = fetch_issues(repo, token, labels=labels, page=page)
        matches.extend(filter_issues_by_query(issues, query))
        if limit is not None and len(matches) >= limit:
            return matches[:limit]
        if not issues:
            break
    return matches


def find_dedup_comment(comments: list[dict[str, Any]]) -> dict[str, Any] | None:
    for comment in comments:
        body = str(comment.get("body") or "")
        if issue_dedup.SIMILAR_ISSUES_MARKER in body:
            return comment
    return None


def extract_similar_issue_refs(comment_body: str) -> list[SimilarIssueRef]:
    refs: list[SimilarIssueRef] = []
    link_pattern = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<url>[^)]+)\)")
    number_pattern = re.compile(r"#(?P<number>\d+)")
    for line in comment_body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        content = stripped[2:]
        title: str | None = None
        if " - " in content:
            ref_part, rest = content.split(" - ", 1)
            title = rest.rsplit(" (", 1)[0].strip() if " (" in rest else rest.strip()
        else:
            ref_part = content
        url = None
        number = None
        link_match = link_pattern.search(ref_part)
        if link_match:
            url = link_match.group("url").strip()
            label = link_match.group("label")
            number_match = number_pattern.search(label)
            if number_match:
                number = int(number_match.group("number"))
        else:
            number_match = number_pattern.search(ref_part)
            if number_match:
                number = int(number_match.group("number"))
        if number is None and url is None:
            continue
        refs.append(SimilarIssueRef(number=number, url=url, title=title or None))
    return refs


def format_duplicate_confirmation(refs: list[SimilarIssueRef]) -> str:
    if refs:
        first = refs[0]
        if first.number is not None:
            return f"Duplicate detected and linked to #{first.number}."
        if first.url:
            return f"Duplicate detected and linked to {first.url}."
    return "Duplicate detected and linked to similar issue(s)."


def check_issue_for_duplicate(
    repo: str,
    issue_number: int,
    token: str,
    *,
    attempts: int,
    interval: float,
) -> dict[str, Any] | None:
    remaining = max(attempts, 1)
    while remaining > 0:
        comments = fetch_issue_comments(repo, issue_number, token)
        match = find_dedup_comment(comments)
        if match is not None:
            return match
        remaining -= 1
        if remaining > 0 and interval > 0:
            time.sleep(interval)
    return None


def check_issue_for_no_duplicate(
    repo: str,
    issue_number: int,
    token: str,
    *,
    attempts: int,
    interval: float,
) -> bool:
    remaining = max(attempts, 1)
    while remaining > 0:
        comments = fetch_issue_comments(repo, issue_number, token)
        if find_dedup_comment(comments) is not None:
            return False
        remaining -= 1
        if remaining > 0 and interval > 0:
            time.sleep(interval)
    return True


def _parse_labels(value: str | None) -> list[str] | None:
    if not value:
        return None
    labels = [label.strip() for label in value.split(",") if label.strip()]
    return labels or None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create GitHub issues for agents-dedup smoke testing."
    )
    parser.add_argument("--repo", required=True, help="Repository in owner/name form.")
    parser.add_argument(
        "--token-env",
        default="GITHUB_TOKEN",
        help="Environment variable containing the GitHub token.",
    )
    parser.add_argument("--labels", help="Comma-separated labels to add to the issue.")
    parser.add_argument(
        "--source-issue",
        type=int,
        help="Issue number to duplicate (uses its title/body).",
    )
    parser.add_argument(
        "--find-issue",
        help="Substring to search for in open issue titles/bodies.",
    )
    parser.add_argument(
        "--find-labels",
        help="Comma-separated labels to filter source issues.",
    )
    parser.add_argument(
        "--find-pages",
        type=int,
        default=1,
        help="Number of issue pages to scan when searching.",
    )
    parser.add_argument(
        "--find-limit",
        type=int,
        help="Maximum number of matching issues to list.",
    )
    parser.add_argument("--title", help="Title for a new issue (required if no source).")
    parser.add_argument("--body", help="Body for a new issue (optional).")
    parser.add_argument(
        "--title-suffix",
        default="",
        help="Suffix to append to the source issue title when duplicating.",
    )
    parser.add_argument(
        "--note",
        help="Optional note appended to the duplicated issue body.",
    )
    parser.add_argument(
        "--check-issue",
        type=int,
        help="Issue number to check for a duplicate-detection comment.",
    )
    parser.add_argument(
        "--check-unique",
        type=int,
        help="Issue number to confirm no duplicate-detection comment is present.",
    )
    parser.add_argument(
        "--check-attempts",
        type=int,
        default=1,
        help="Number of attempts to check for a duplicate comment.",
    )
    parser.add_argument(
        "--check-interval",
        type=float,
        default=0.0,
        help="Seconds to wait between duplicate-check attempts.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the payload instead of creating an issue.",
    )
    parser.add_argument(
        "--show-source",
        action="store_true",
        help="Print the source issue selection and exit.",
    )
    parser.add_argument(
        "--list-issues",
        action="store_true",
        help="List matching source issues and exit.",
    )
    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    token = os.environ.get(args.token_env)
    if not token:
        print(f"Missing GitHub token in ${args.token_env}.", file=sys.stderr)
        return 1

    labels = _parse_labels(args.labels)
    find_labels = _parse_labels(args.find_labels)

    if args.check_issue is not None and args.check_unique is not None:
        print("Choose only one of --check-issue or --check-unique.", file=sys.stderr)
        return 1

    if args.check_issue is not None:
        comment = check_issue_for_duplicate(
            args.repo,
            args.check_issue,
            token,
            attempts=args.check_attempts,
            interval=args.check_interval,
        )
        if comment is None:
            print("Duplicate detection comment not found.")
            return 1
        comment_body = str(comment.get("body") or "")
        refs = extract_similar_issue_refs(comment_body)
        print(format_duplicate_confirmation(refs))
        comment_url = comment.get("html_url") or comment.get("url") or "unknown"
        print(f"Duplicate detection comment found: {comment_url}")
        return 0
    if args.check_unique is not None:
        is_unique = check_issue_for_no_duplicate(
            args.repo,
            args.check_unique,
            token,
            attempts=args.check_attempts,
            interval=args.check_interval,
        )
        if not is_unique:
            print("Duplicate detection comment found (unique check failed).")
            return 1
        print("Unique issue accepted without duplicate flags.")
        print("No duplicate detection comment found.")
        return 0

    if args.list_issues:
        matches = collect_matching_issues(
            args.repo,
            token,
            query=args.find_issue,
            labels=find_labels,
            pages=args.find_pages,
            limit=args.find_limit,
        )
        if not matches:
            print("No matching source issue found.", file=sys.stderr)
            return 1
        for match in matches:
            issue_url = match.url or "unknown"
            print(f"#{match.number} {match.title} ({issue_url})")
        return 0

    source_issue = None
    if args.source_issue is not None:
        source_issue = fetch_issue(args.repo, args.source_issue, token)
    elif args.find_issue:
        source_issue = find_source_issue(
            args.repo,
            token,
            query=args.find_issue,
            labels=find_labels,
            pages=args.find_pages,
        )
        if source_issue is None:
            print("No matching source issue found.", file=sys.stderr)
            return 1

    if source_issue is not None:
        if args.show_source:
            issue_url = source_issue.url or "unknown"
            print(f"Source issue: #{source_issue.number} {source_issue.title} ({issue_url})")
            return 0
        payload = build_duplicate_payload(
            source_issue,
            title_suffix=args.title_suffix,
            note=args.note,
            labels=labels,
        )
    else:
        if not args.title:
            print("Either --source-issue/--find-issue or --title is required.", file=sys.stderr)
            return 1
        payload = build_issue_payload(args.title, args.body, labels)

    if args.dry_run:
        print(payload)
        return 0

    created = _request_json(
        "POST",
        f"{GITHUB_API}/repos/{args.repo}/issues",
        token,
        payload=payload,
    )
    if not isinstance(created, dict):
        print("GitHub API did not return a JSON object for the new issue.", file=sys.stderr)
        return 1

    issue_url = created.get("html_url") or created.get("url") or "unknown"
    print(f"Issue created: {issue_url}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main(sys.argv[1:]))
