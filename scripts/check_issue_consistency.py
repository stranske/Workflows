#!/usr/bin/env python3
"""Check issue number consistency between PR title, commits, and file headers."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ISSUE_WORD_PATTERN = re.compile(r"issue\s*[:#-]?\s*(\d+)", re.IGNORECASE)
ISSUE_SLUG_PATTERN = re.compile(r"issue[-_](\d+)", re.IGNORECASE)
HASH_PATTERN = re.compile(r"#(\d+)")


def _is_pr_marker_before_hash(prefix: str) -> bool:
    if not prefix:
        return False
    tail = prefix[-20:]
    return re.search(r"(?:^|\W)pr[\W\s]*$", tail, re.IGNORECASE) is not None


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


def extract_title_issue_number(title: str) -> int | None:
    title = title or ""
    for match in HASH_PATTERN.finditer(title):
        start = match.start()
        prefix = title[:start]
        if _is_pr_marker_before_hash(prefix):
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


def is_autofix_context(pr_title: str, head_ref: str) -> bool:
    combined = f"{pr_title or ''}\n{head_ref or ''}".lower()
    return "autofix" in combined or (head_ref or "").lower().startswith("autofix/")


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


def collect_commit_messages(
    base_ref: str | None, base_sha: str | None, base_remote: str
) -> list[str]:
    if base_sha:
        output = _run_git(["log", "--format=%s", f"{base_sha}..HEAD"])
    elif base_ref:
        range_spec = f"{base_remote}/{base_ref}..HEAD"
        output = _run_git(["log", "--format=%s", range_spec])
    else:
        output = _run_git(["log", "--format=%s", "-n", "20"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def collect_changed_files(
    base_ref: str | None, base_sha: str | None, base_remote: str
) -> list[Path]:
    if base_sha:
        output = _run_git(["diff", "--name-only", f"{base_sha}...HEAD"])
    elif base_ref:
        range_spec = f"{base_remote}/{base_ref}...HEAD"
        output = _run_git(["diff", "--name-only", range_spec])
    else:
        output = _run_git(["diff", "--name-only", "HEAD~1..HEAD"])
    return [Path(line.strip()) for line in output.splitlines() if line.strip()]


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

    pr_issue = extract_title_issue_number(args.pr_title)
    if not pr_issue:
        head_numbers = extract_head_ref_issue_numbers(args.head_ref)
        if len(head_numbers) == 1:
            pr_issue = next(iter(head_numbers))
        elif len(head_numbers) > 1:
            print(
                "Error: Multiple issue numbers detected in head ref:",
                sorted(head_numbers),
                file=sys.stderr,
            )
            return 1
        elif is_autofix_context(args.pr_title, args.head_ref):
            print("Skipping issue consistency check: autofix context with no issue number.")
            return 0
        else:
            print("Error: Unable to determine issue number from PR title.", file=sys.stderr)
            return 1

    base_sha = (args.base_sha or "").strip() or None
    base_remote = (args.base_remote or "origin").strip() or "origin"
    commit_messages = collect_commit_messages(args.base_ref, base_sha, base_remote)
    commit_issue_numbers: set[int] = set()
    for message in commit_messages:
        commit_issue_numbers.update(extract_issue_numbers(message, include_hash=True))

    mismatched_commits = sorted(num for num in commit_issue_numbers if num != pr_issue)
    if mismatched_commits:
        print(
            "Error: Commit messages reference issue numbers that do not match PR title:",
            mismatched_commits,
            file=sys.stderr,
        )
        return 1

    changed_files = collect_changed_files(args.base_ref, base_sha, base_remote)
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
