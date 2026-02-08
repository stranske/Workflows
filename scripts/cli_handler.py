from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from scripts import api_client, auth_validator
from scripts.duplicate_detection import (
    build_duplicate_payload,
    build_issue_payload,
    check_issue_for_duplicate,
    check_issue_for_no_duplicate,
    collect_matching_issues,
    extract_similar_issue_refs,
    find_source_issue,
    format_duplicate_confirmation,
    format_source_confirmation,
    format_source_issue_line,
    matches_expected_duplicate,
)


def _parse_labels(value: str | None) -> list[str] | None:
    if not value:
        return None
    labels = [label.strip() for label in value.split(",") if label.strip()]
    return labels or None


def _parse_allowlist(value: str | None) -> set[str]:
    if not value:
        return set()
    return {entry.strip() for entry in value.split(",") if entry.strip()}


def _parse_scopes(value: str | None) -> set[str]:
    if not value:
        return set()
    return {scope.strip() for scope in value.split(",") if scope.strip()}


def _load_config(config_path: str | None, config_env: str) -> dict[str, object]:
    path_value = config_path or os.environ.get(config_env)
    if not path_value:
        return {}
    config_file = Path(path_value)

    if not config_file.exists():
        print(f"Config file not found: {config_file}", file=sys.stderr)
        return {}
    try:
        payload = json.loads(config_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid config JSON in {config_file}: {exc}", file=sys.stderr)
        return {}
    if not isinstance(payload, dict):
        print(f"Config must be a JSON object: {config_file}", file=sys.stderr)
        return {}
    return payload


def _load_allowlist(
    allowlist_value: str | None, allowlist_env: str, config: dict[str, object]
) -> set[str]:
    allowlist = _parse_allowlist(allowlist_value)
    if allowlist:
        return allowlist
    allowlist = _parse_allowlist(os.environ.get(allowlist_env))
    if allowlist:
        return allowlist
    config_value = config.get("allowlist")
    if isinstance(config_value, list):
        return {str(entry).strip() for entry in config_value if str(entry).strip()}
    if isinstance(config_value, str):
        return _parse_allowlist(config_value)
    return set()


def _load_allowed_scopes(
    scopes_value: str | None, scopes_env: str, config: dict[str, object]
) -> set[str]:
    scopes = _parse_scopes(scopes_value)
    if scopes:
        return scopes
    scopes = _parse_scopes(os.environ.get(scopes_env))
    if scopes:
        return scopes
    config_value = config.get("allowed_scopes")
    if isinstance(config_value, list):
        return {str(entry).strip() for entry in config_value if str(entry).strip()}
    if isinstance(config_value, str):
        return _parse_scopes(config_value)
    return set()


def _confirm_issue_creation(repo: str, title: str, *, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print("Confirmation required; re-run with --yes to proceed.", file=sys.stderr)
        return False
    response = input(f"Create issue in {repo} titled '{title}'? [y/N]: ").strip().lower()
    return response in {"y", "yes"}


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
    parser.add_argument(
        "--allowlist",
        help="Comma-separated list of allowed repositories (owner/name).",
    )
    parser.add_argument(
        "--config",
        help="Path to a JSON config file containing allowlist/scopes.",
    )
    parser.add_argument(
        "--config-env",
        default="ISSUE_DEDUP_SMOKE_CONFIG",
        help="Environment variable containing the config file path.",
    )
    parser.add_argument(
        "--allowlist-env",
        default="ISSUE_DEDUP_SMOKE_ALLOWLIST",
        help="Environment variable containing the repository allowlist.",
    )
    parser.add_argument(
        "--allowed-scopes",
        help="Comma-separated OAuth scopes allowed for the token.",
    )
    parser.add_argument(
        "--allowed-scopes-env",
        default="ISSUE_DEDUP_SMOKE_ALLOWED_SCOPES",
        help="Environment variable containing allowed OAuth scopes.",
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
        "--expected-issue-number",
        type=int,
        help="Expected duplicate issue number to confirm is linked.",
    )
    parser.add_argument(
        "--expected-issue-url",
        help="Expected duplicate issue URL to confirm is linked.",
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
        "--retry-attempts",
        type=int,
        default=api_client.DEFAULT_RETRY_ATTEMPTS,
        help="Number of attempts for GitHub API requests.",
    )
    parser.add_argument(
        "--retry-backoff",
        type=float,
        default=api_client.DEFAULT_RETRY_BACKOFF,
        help="Base seconds for exponential backoff between API retries.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the payload instead of creating an issue.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt before creating an issue.",
    )
    parser.add_argument(
        "--show-source",
        action="store_true",
        help="Print the source issue selection and exit.",
    )
    parser.add_argument(
        "--confirm-source",
        action="store_true",
        help="Confirm the source issue selection and exit.",
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

    config = _load_config(args.config, args.config_env)
    allowlist = _load_allowlist(args.allowlist, args.allowlist_env, config)
    if not allowlist:
        print(
            f"Repository allowlist is empty. Set --allowlist, ${args.allowlist_env}, or --config.",
            file=sys.stderr,
        )
        return 1
    if args.repo not in allowlist:
        print(f"Repository {args.repo} is not in the allowlist.", file=sys.stderr)
        return 1

    token = os.environ.get(args.token_env)
    if not token:
        print(f"Missing GitHub token in ${args.token_env}.", file=sys.stderr)
        return 1

    allowed_scopes = _load_allowed_scopes(args.allowed_scopes, args.allowed_scopes_env, config)
    if allowed_scopes:
        scopes = api_client.fetch_oauth_scopes(
            token,
            retry_attempts=args.retry_attempts,
            retry_backoff=args.retry_backoff,
        )
        payload = {"scopes": scopes, "allowed_scopes": allowed_scopes}
        validation = auth_validator.validate_auth_payload(
            payload,
            require_allowed_scopes=True,
            require_all_scopes=True,
        )
        if validation.skipped:
            if validation.message:
                print(validation.message, file=sys.stderr)
        elif not validation.valid:
            if validation.message:
                print(validation.message, file=sys.stderr)
            return 1

    labels = _parse_labels(args.labels)
    find_labels = _parse_labels(args.find_labels)

    if args.check_issue is not None and args.check_unique is not None:
        print("Choose only one of --check-issue or --check-unique.", file=sys.stderr)
        return 1
    if args.check_issue is None and (args.expected_issue_number or args.expected_issue_url):
        print("Expected issue match requires --check-issue.", file=sys.stderr)
        return 1
    if args.show_source and args.confirm_source:
        print("Choose only one of --show-source or --confirm-source.", file=sys.stderr)
        return 1

    if args.check_issue is not None:
        comment = check_issue_for_duplicate(
            args.repo,
            args.check_issue,
            token,
            attempts=args.check_attempts,
            interval=args.check_interval,
            retry_attempts=args.retry_attempts,
            retry_backoff=args.retry_backoff,
        )
        if comment is None:
            print("Duplicate detection comment not found.")
            return 1
        comment_body = str(comment.get("body") or "")
        refs = extract_similar_issue_refs(comment_body)
        if not matches_expected_duplicate(
            refs,
            expected_number=args.expected_issue_number,
            expected_url=args.expected_issue_url,
        ):
            print("Expected duplicate link not found.", file=sys.stderr)
            return 1
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
            retry_attempts=args.retry_attempts,
            retry_backoff=args.retry_backoff,
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
            retry_attempts=args.retry_attempts,
            retry_backoff=args.retry_backoff,
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
        source_issue = api_client.fetch_issue(
            args.repo,
            args.source_issue,
            token,
            retry_attempts=args.retry_attempts,
            retry_backoff=args.retry_backoff,
        )
    elif args.find_issue:
        source_issue = find_source_issue(
            args.repo,
            token,
            query=args.find_issue,
            labels=find_labels,
            pages=args.find_pages,
            retry_attempts=args.retry_attempts,
            retry_backoff=args.retry_backoff,
        )
        if source_issue is None:
            print("No matching source issue found.", file=sys.stderr)
            return 1

    if source_issue is not None:
        if args.show_source:
            print(format_source_issue_line(source_issue))
            return 0
        if args.confirm_source:
            print(format_source_confirmation(source_issue))
            return 0
        payload = build_duplicate_payload(
            source_issue,
            title_suffix=args.title_suffix,
            note=args.note,
            labels=labels,
        )
    else:
        if args.show_source or args.confirm_source:
            print("Source issue details are required to confirm selection.", file=sys.stderr)
            return 1
        if not args.title:
            print("Either --source-issue/--find-issue or --title is required.", file=sys.stderr)
            return 1
        payload = build_issue_payload(args.title, args.body, labels)

    if args.dry_run:
        print(payload)
        return 0

    if not _confirm_issue_creation(args.repo, payload["title"], assume_yes=args.yes):
        print("Issue creation cancelled.", file=sys.stderr)
        return 1

    created = api_client.create_issue(
        args.repo,
        token,
        payload["title"],
        payload.get("body"),
        labels,
        retry_attempts=args.retry_attempts,
        retry_backoff=args.retry_backoff,
    )
    issue_url = created.get("html_url") or created.get("url") or "unknown"
    print(f"Issue created: {issue_url}")
    return 0
