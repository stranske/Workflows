from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from scripts import api_client
from scripts.langchain import issue_dedup


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
        issues = api_client.fetch_issues(repo, token, labels=labels, page=page)
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
        issues = api_client.fetch_issues(repo, token, labels=labels, page=page)
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


def format_source_issue_line(source_issue: SourceIssue) -> str:
    issue_url = source_issue.url or "unknown"
    return f"Source issue: #{source_issue.number} {source_issue.title} ({issue_url})"


def format_source_confirmation(source_issue: SourceIssue) -> str:
    issue_url = source_issue.url or "unknown"
    return f"Source issue confirmed: #{source_issue.number} {source_issue.title} ({issue_url})"


def format_duplicate_confirmation(refs: list[SimilarIssueRef]) -> str:
    if refs:
        first = refs[0]
        if first.number is not None:
            return f"Duplicate detected and linked to #{first.number}."
        if first.url:
            return f"Duplicate detected and linked to {first.url}."
    return "Duplicate detected and linked to similar issue(s)."


def matches_expected_duplicate(
    refs: list[SimilarIssueRef],
    *,
    expected_number: int | None,
    expected_url: str | None,
) -> bool:
    if expected_number is None and not expected_url:
        return True
    normalized_url = expected_url.rstrip("/") if expected_url else None
    for ref in refs:
        if expected_number is not None and ref.number == expected_number:
            return True
        if normalized_url and ref.url and ref.url.rstrip("/") == normalized_url:
            return True
    return False


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
        comments = api_client.fetch_issue_comments(repo, issue_number, token)
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
        comments = api_client.fetch_issue_comments(repo, issue_number, token)
        if find_dedup_comment(comments) is not None:
            return False
        remaining -= 1
        if remaining > 0 and interval > 0:
            time.sleep(interval)
    return True
