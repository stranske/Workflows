#!/usr/bin/env python3
"""Check issue number consistency between PR title, commits, and file headers."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ISSUE_WORD_PATTERN = re.compile(r"issue\s*[:#-]?\s*(\d+)", re.IGNORECASE)
ISSUE_SLUG_PATTERN = re.compile(r"issue[-_](\d+)", re.IGNORECASE)
HASH_PATTERN = re.compile(r"#(\d+)")
MERGE_COMMIT_PATTERN = re.compile(
    r"^merge\s+(?:pull request|branch|remote-tracking branch)\b",
    re.IGNORECASE,
)
IGNORE_COMMIT_PATTERNS = (re.compile(r"^chore\(ledger\)", re.IGNORECASE),)


def _is_pr_marker_before_hash(prefix: str) -> bool:
    if not prefix:
        return False
    tail = prefix[-20:]
    return re.search(r"(?:^|\W)pr[\W\s]*$", tail, re.IGNORECASE) is not None


def _is_issue_marker_before_hash(prefix: str) -> bool:
    if not prefix:
        return False
    tail = prefix[-20:]
    return re.search(r"(?:^|\W)issue[\W\s]*$", tail, re.IGNORECASE) is not None


def _hash_mentions(text: str) -> set[int]:
    matches = set()
    for match in HASH_PATTERN.finditer(text or ""):
        start = match.start()
        prefix = (text or "")[:start]
        if _is_pr_marker_before_hash(prefix):
            continue
        matches.add(int(match.group(1)))
    return matches


def extract_issue_numbers(text: str, *, include_hash: bool = True) -> set[int]:
    numbers = set()
    for match in ISSUE_WORD_PATTERN.findall(text or ""):
        numbers.add(int(match))
    for match in ISSUE_SLUG_PATTERN.findall(text or ""):
        numbers.add(int(match))
    if include_hash:
        numbers.update(_hash_mentions(text or ""))
    return numbers


def _is_ignored_commit_message(message: str) -> bool:
    if not message:
        return False
    if MERGE_COMMIT_PATTERN.search(message):
        return True
    return any(pattern.search(message) for pattern in IGNORE_COMMIT_PATTERNS)


def extract_commit_issue_numbers(messages: list[str]) -> set[int]:
    numbers: set[int] = set()
    for message in messages:
        if _is_ignored_commit_message(message):
            continue
        numbers.update(extract_issue_numbers(message, include_hash=False))
    return numbers


def extract_title_issue_number(title: str) -> int | None:
    title = title or ""
    for match in HASH_PATTERN.finditer(title):
        start = match.start()
        prefix = title[:start]
        if _is_pr_marker_before_hash(prefix):
            continue
        if AUTO_FIX_PATTERN.search(title) and not _is_issue_marker_before_hash(prefix):
            continue
        return int(match.group(1))
    word_match = ISSUE_WORD_PATTERN.search(title)
    slug_match = ISSUE_SLUG_PATTERN.search(title)
    chosen = None
    if word_match and slug_match:
        chosen = word_match if word_match.start() <= slug_match.start() else slug_match
    else:
        chosen = word_match or slug_match
    if chosen:
        return int(chosen.group(1))
    return None


def extract_head_ref_issue_numbers(head_ref: str) -> set[int]:
    return extract_issue_numbers(head_ref or "", include_hash=False)


def resolve_head_ref_issue_number(head_ref: str) -> tuple[int | None, bool]:
    numbers = extract_head_ref_issue_numbers(head_ref)
    if len(numbers) == 1:
        return next(iter(numbers)), False
    if len(numbers) > 1:
        return None, True
    return None, False


AUTO_FIX_PATTERN = re.compile(r"auto[\s-]?fix", re.IGNORECASE)


def _load_event_payload(event_path: str | None) -> dict:
    if not event_path:
        return {}
    try:
        with open(event_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _extract_pull_request(payload: dict) -> dict:
    pull_request = payload.get("pull_request")
    if isinstance(pull_request, dict):
        return pull_request
    pull_requests = payload.get("pull_requests")
    if isinstance(pull_requests, list) and pull_requests:
        first = pull_requests[0]
        if isinstance(first, dict):
            return first
    return {}


def _has_autofix_label(event_path: str | None) -> bool:
    payload = _load_event_payload(event_path)
    if not payload:
        return False
    pull_request = _extract_pull_request(payload)
    if not pull_request:
        return False
    labels = pull_request.get("labels") or []
    for label in labels:
        name = label.get("name", "") if isinstance(label, dict) else str(label)
        if AUTO_FIX_PATTERN.search(name or ""):
            return True
    return False


def is_autofix_context(pr_title: str, head_ref: str, event_path: str | None = None) -> bool:
    combined = f"{pr_title or ''}\n{head_ref or ''}"
    if AUTO_FIX_PATTERN.search(combined) or AUTO_FIX_PATTERN.match(head_ref or ""):
        return True
    if event_path is None:
        event_path = os.environ.get("GITHUB_EVENT_PATH")
    return _has_autofix_label(event_path)


def resolve_pr_context(
    pr_title: str, head_ref: str, event_path: str | None = None
) -> tuple[str, str]:
    title = pr_title or ""
    head = head_ref or ""
    if event_path is None:
        event_path = os.environ.get("GITHUB_EVENT_PATH")
    payload = _load_event_payload(event_path)
    pull_request = _extract_pull_request(payload)
    if not title and pull_request:
        title = str(pull_request.get("title", "") or "")
    if not head and pull_request:
        head_payload = pull_request.get("head")
        if isinstance(head_payload, dict):
            head = str(head_payload.get("ref", "") or "")
    if not head:
        workflow_run = payload.get("workflow_run")
        if isinstance(workflow_run, dict):
            head = str(workflow_run.get("head_branch", "") or "")
    return title, head


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def _remote_exists(name: str) -> bool:
    if not name:
        return False
    try:
        _run_git(["remote", "get-url", name])
    except RuntimeError:
        return False
    return True


def _resolve_base_remote(base_remote: str | None) -> str:
    candidate = (base_remote or "origin").strip() or "origin"
    if _remote_exists(candidate):
        return candidate
    for fallback in ("origin", "upstream"):
        if fallback != candidate and _remote_exists(fallback):
            return fallback
    return candidate


def _remote_ref_exists(remote: str, ref: str) -> bool:
    if not remote or not ref:
        return False
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/{remote}/{ref}"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _find_remote_with_ref(base_remote: str, base_ref: str) -> str | None:
    for candidate in (base_remote, "origin", "upstream"):
        if candidate and _remote_ref_exists(candidate, base_ref):
            return candidate
    return None


def _should_use_fallback(message: str, fallback: list[str] | None) -> bool:
    if not fallback:
        return False
    lowered = message.lower()
    return any(
        snippet in lowered
        for snippet in (
            "no merge base",
            "bad object",
            "invalid object name",
            "not a valid object name",
            "ambiguous argument",
            "unknown revision",
            "not in the working tree",
        )
    )


def _run_git_with_fallback(primary: list[str], fallback: list[str] | None) -> str:
    try:
        return _run_git(primary)
    except RuntimeError as exc:
        if _should_use_fallback(str(exc), fallback):
            return _run_git(fallback)
        raise


def _run_git_with_fallback_and_flag(
    primary: list[str], fallback: list[str] | None
) -> tuple[str, bool]:
    try:
        return _run_git(primary), False
    except RuntimeError as exc:
        if _should_use_fallback(str(exc), fallback):
            return _run_git(fallback), True
        raise


def collect_commit_messages(
    base_ref: str | None, base_sha: str | None, base_remote: str
) -> tuple[list[str], bool]:
    resolved_remote = None
    used_fallback = False
    if base_ref:
        resolved_remote = _find_remote_with_ref(base_remote, base_ref)
    if base_sha:
        fallback = None
        if base_ref:
            if resolved_remote:
                fallback = ["log", "--format=%s", f"{resolved_remote}/{base_ref}..HEAD"]
            else:
                fallback = ["log", "--format=%s", "-n", "20"]
        else:
            fallback = ["log", "--format=%s", "-n", "20"]
        output, used_fallback = _run_git_with_fallback_and_flag(
            ["log", "--format=%s", f"{base_sha}..HEAD"],
            fallback,
        )
    elif base_ref:
        if resolved_remote:
            range_spec = f"{resolved_remote}/{base_ref}..HEAD"
            output = _run_git(["log", "--format=%s", range_spec])
        else:
            output = _run_git(["log", "--format=%s", "-n", "20"])
            used_fallback = True
    else:
        output = _run_git(["log", "--format=%s", "-n", "20"])
        used_fallback = True
    return [line.strip() for line in output.splitlines() if line.strip()], used_fallback


def collect_changed_files(
    base_ref: str | None, base_sha: str | None, base_remote: str
) -> tuple[list[Path], bool]:
    resolved_remote = None
    used_fallback = False
    if base_ref:
        resolved_remote = _find_remote_with_ref(base_remote, base_ref)
    if base_sha:
        fallback = None
        if base_ref:
            if resolved_remote:
                fallback = ["diff", "--name-only", f"{resolved_remote}/{base_ref}...HEAD"]
            else:
                fallback = ["diff", "--name-only", "HEAD~20..HEAD"]
        else:
            fallback = ["diff", "--name-only", "HEAD~20..HEAD"]
        output, used_fallback = _run_git_with_fallback_and_flag(
            ["diff", "--name-only", f"{base_sha}...HEAD"],
            fallback,
        )
    elif base_ref:
        if resolved_remote:
            range_spec = f"{resolved_remote}/{base_ref}...HEAD"
            output = _run_git(["diff", "--name-only", range_spec])
        else:
            output = _run_git(["diff", "--name-only", "HEAD~20..HEAD"])
            used_fallback = True
    else:
        output = _run_git(["diff", "--name-only", "HEAD~20..HEAD"])
        used_fallback = True
    return [Path(line.strip()) for line in output.splitlines() if line.strip()], used_fallback


def collect_header_issue_numbers(file_path: Path, max_lines: int) -> set[int]:
    numbers: set[int] = set()
    in_docstring = False
    docstring_delim = ""

    def is_comment_line(line: str) -> bool:
        stripped = line.lstrip()
        return stripped.startswith(("#", "//", "/*", "*", "--", ";", "<!--"))

    try:
        with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for _ in range(max_lines):
                line = handle.readline()
                if not line:
                    break
                if in_docstring:
                    if "issue" in line.lower():
                        numbers.update(extract_issue_numbers(line, include_hash=True))
                    if docstring_delim and docstring_delim in line:
                        in_docstring = False
                        docstring_delim = ""
                    continue

                stripped = line.lstrip()
                if stripped.startswith(('"""', "'''")):
                    docstring_delim = stripped[:3]
                    in_docstring = True
                    if "issue" in line.lower():
                        numbers.update(extract_issue_numbers(line, include_hash=True))
                    if stripped.count(docstring_delim) >= 2:
                        in_docstring = False
                        docstring_delim = ""
                    continue

                if not is_comment_line(line):
                    continue
                if "issue" not in line.lower():
                    continue
                numbers.update(extract_issue_numbers(line, include_hash=True))
    except (OSError, UnicodeError):
        return numbers
    return numbers


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify issue number consistency between PR title, commits, and file headers."
    )
    parser.add_argument(
        "--base-ref",
        default=os.environ.get("BASE_REF") or os.environ.get("GITHUB_BASE_REF"),
        help="Base branch ref for diff range (defaults to GITHUB_BASE_REF).",
    )
    parser.add_argument(
        "--base-sha",
        default=os.environ.get("BASE_SHA") or os.environ.get("GITHUB_BASE_SHA"),
        help="Base commit SHA for diff range (preferred when available).",
    )
    parser.add_argument(
        "--base-remote",
        default=os.environ.get("BASE_REMOTE", "origin"),
        help="Git remote name to use for base branch comparisons.",
    )
    parser.add_argument(
        "--pr-title",
        default=os.environ.get("PR_TITLE", ""),
        help="Pull request title (defaults to PR_TITLE env).",
    )
    parser.add_argument(
        "--head-ref",
        default=os.environ.get("HEAD_REF") or os.environ.get("GITHUB_HEAD_REF", ""),
        help="Pull request head ref (defaults to HEAD_REF or GITHUB_HEAD_REF env).",
    )
    parser.add_argument(
        "--header-lines",
        type=int,
        default=40,
        help="Number of header lines to scan in each file.",
    )
    args = parser.parse_args()

    base_sha = (args.base_sha or "").strip() or None
    base_remote = _resolve_base_remote(args.base_remote)
    pr_title, head_ref = resolve_pr_context(args.pr_title, args.head_ref)
    pr_issue = extract_title_issue_number(pr_title)
    if not pr_issue:
        pr_issue, head_ambiguous = resolve_head_ref_issue_number(head_ref)
        if head_ambiguous:
            print(
                "Warning: Multiple issue numbers detected in head ref; "
                "ignoring head ref and falling back to commits/headers.",
                file=sys.stderr,
            )
        if not pr_issue:
            if is_autofix_context(pr_title, head_ref):
                print("Skipping issue consistency check: autofix context with no issue number.")
                return 0
            commit_messages, commit_fallback = collect_commit_messages(
                args.base_ref, base_sha, base_remote
            )
            commit_issue_numbers = extract_commit_issue_numbers(commit_messages)

            changed_files, file_fallback = collect_changed_files(
                args.base_ref, base_sha, base_remote
            )
            header_issue_numbers: set[int] = set()
            for file_path in changed_files:
                if not file_path.exists() or not file_path.is_file():
                    continue
                header_issue_numbers.update(
                    collect_header_issue_numbers(file_path, args.header_lines)
                )

            combined_issue_numbers = commit_issue_numbers | header_issue_numbers
            fallback_used = commit_fallback or file_fallback
            if len(combined_issue_numbers) == 1:
                pr_issue = next(iter(combined_issue_numbers))
            elif not combined_issue_numbers:
                print("Skipping issue consistency check: no issue references found.")
                return 0
            else:
                if fallback_used:
                    print(
                        "Skipping issue consistency check: "
                        "unable to determine issue number from PR title with fallback diff range."
                    )
                    return 0
                print("Error: Unable to determine issue number from PR title.", file=sys.stderr)
                return 1

    commit_messages, commit_fallback = collect_commit_messages(args.base_ref, base_sha, base_remote)
    commit_issue_numbers = extract_commit_issue_numbers(commit_messages)

    changed_files, file_fallback = collect_changed_files(args.base_ref, base_sha, base_remote)
    fallback_used = commit_fallback or file_fallback
    if fallback_used:
        print(
            "Skipping issue consistency check: base reference unavailable for reliable comparison."
        )
        return 0

    mismatched_commits = sorted(num for num in commit_issue_numbers if num != pr_issue)
    if mismatched_commits:
        print(
            "Error: Commit messages reference issue numbers that do not match PR title:",
            mismatched_commits,
            file=sys.stderr,
        )
        return 1

    header_issue_numbers: set[int] = set()
    mismatched_files: list[str] = []
    for file_path in changed_files:
        if not file_path.exists() or not file_path.is_file():
            continue
        numbers = collect_header_issue_numbers(file_path, args.header_lines)
        header_issue_numbers.update(numbers)
        if any(num != pr_issue for num in numbers):
            mismatched_files.append(str(file_path))

    if mismatched_files:
        print(
            "Error: File headers reference issue numbers that do not match PR title:",
            ", ".join(sorted(mismatched_files)),
            file=sys.stderr,
        )
        return 1

    print(
        f"Issue consistency check passed for #{pr_issue}. "
        f"Checked {len(commit_messages)} commit message(s) and {len(changed_files)} file(s)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
