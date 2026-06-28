#!/usr/bin/env python3
"""Fail Gate on weak added tests or obvious secrets in the full PR diff."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

TEST_FILE_RE = re.compile(r"(^|/)(test_[^/]+\.py|[^/]+_test\.(js|ts|tsx))$")
LITERAL_ASSERTION_RE = re.compile(
    r"""
    (
      \bassert\s+.+?(==|!=|>=|<=|>|<| in | not\ in )\s*["'\d\[\{(]
      |pytest\.raises\(
      |expect\(.+?\)\.to(?:Equal|Be|Contain|Match)\(\s*["'\d\[\{(]
      |assert\.(?:equal|deepEqual|strictEqual|match)\(
    )
    """,
    re.VERBOSE,
)
SECRET_PATTERNS = {
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "openai-key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private-key": re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def _git_lines(args: list[str]) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def _changed_files(base: str, head: str) -> list[str]:
    return _git_lines(["diff", "--name-only", "--diff-filter=AM", f"{base}...{head}"])


def _full_diff(base: str, head: str) -> str:
    completed = subprocess.run(
        ["git", "diff", "--no-ext-diff", "--unified=0", f"{base}...{head}"],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def is_test_file(path: str) -> bool:
    return bool(TEST_FILE_RE.search(path))


def has_literal_expected_assertion(text: str) -> bool:
    return bool(LITERAL_ASSERTION_RE.search(text))


def scan_weak_test_files(file_texts: Mapping[str, str]) -> list[str]:
    return [
        file_name
        for file_name, text in file_texts.items()
        if is_test_file(file_name) and not has_literal_expected_assertion(text)
    ]


def _weak_added_tests(files: list[str]) -> list[str]:
    file_texts: dict[str, str] = {}
    for file_name in files:
        if not is_test_file(file_name):
            continue
        path = Path(file_name)
        if not path.is_file():
            continue
        file_texts[file_name] = path.read_text(encoding="utf-8")
    return scan_weak_test_files(file_texts)


def scan_secret_patterns(diff_text: str) -> list[str]:
    hits: list[str] = []
    for line in diff_text.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(line):
                hits.append(name)
                break
    return hits


def check_diff_quality(base: str, head: str) -> list[str]:
    failures: list[str] = []
    weak_tests = _weak_added_tests(_changed_files(base, head))
    if weak_tests:
        failures.append(
            "test-quality: added/modified test files without literal expected assertions: "
            + ", ".join(weak_tests)
        )
    # Surface only the *count* of matched patterns: never echo secret values or
    # pattern-derived data into CI logs (clear-text-logging hardening). The gate
    # failing is the signal; the author inspects their own diff to remediate.
    blocked_pattern_count = len(set(scan_secret_patterns(_full_diff(base, head))))
    if blocked_pattern_count:
        failures.append(
            "secret-scan: complete diff contains "
            f"{blocked_pattern_count} blocked secret pattern(s); "
            "inspect the diff and remove them"
        )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args(argv)

    failures = check_diff_quality(args.base, args.head)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("Gate diff quality checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
