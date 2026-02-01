#!/usr/bin/env python3
"""Guardrail check for GitHub API usage in workflows and scripts."""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET_DIRS = (
    ROOT / ".github" / "workflows",
    ROOT / ".github" / "scripts",
    ROOT / "scripts",
)

SKIP_FILES = {
    ROOT / ".github" / "scripts" / "github-api-with-retry.js",
    ROOT / ".github" / "scripts" / "token_load_balancer.js",
}

DIRECT_PATTERNS = [
    (re.compile(r"\bgh\s+api\b", re.IGNORECASE), "direct gh api usage"),
    (re.compile(r"api\.github\.com", re.IGNORECASE), "direct api.github.com usage"),
]

API_CALL_PATTERNS = [
    re.compile(r"\b(?:github|client)\.rest\.", re.IGNORECASE),
    re.compile(r"\b(?:github|client)\.paginate\(", re.IGNORECASE),
    re.compile(r"\b(?:github|client)\.request\(", re.IGNORECASE),
    re.compile(r"\boctokit\.request\(", re.IGNORECASE),
]

WRAPPER_HINTS = (
    "createTokenAwareRetry",
    "paginateWithRetry",
    "github-api-with-retry.js",
)

LOAD_BALANCER_HINT = "export-load-balancer-tokens"


def _run_git(args: list[str], allow_exit_codes: set[int] | None = None) -> str:
    allowed = {0} if allow_exit_codes is None else allow_exit_codes
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in allowed:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def _rev_exists(revision: str) -> bool:
    try:
        _run_git(["rev-parse", "--verify", revision])
    except RuntimeError:
        return False
    return True


def _resolve_base_ref(base_ref: str, base_remote: str) -> str | None:
    candidate = f"{base_remote}/{base_ref}"
    if _rev_exists(candidate):
        return candidate
    with contextlib.suppress(RuntimeError):
        _run_git(["fetch", "--depth", "1", base_remote, base_ref])
    if _rev_exists(candidate):
        return candidate
    if _rev_exists(base_ref):
        return base_ref
    return None


def _collect_changed_files(base_ref: str, base_remote: str) -> list[Path]:
    base = _resolve_base_ref(base_ref, base_remote)
    if not base:
        raise RuntimeError(
            f"Unable to resolve base ref '{base_ref}' from '{base_remote}'. "
            "Ensure the base ref is fetched before running the guard."
        )
    if base:
        try:
            output = _run_git(
                ["diff", "--name-only", f"{base}...HEAD"],
                allow_exit_codes={0, 1},
            )
            return [ROOT / line.strip() for line in output.splitlines() if line.strip()]
        except RuntimeError:
            pass
    if _rev_exists("HEAD~1"):
        try:
            output = _run_git(
                ["diff", "--name-only", "HEAD~1...HEAD"],
                allow_exit_codes={0, 1},
            )
            return [ROOT / line.strip() for line in output.splitlines() if line.strip()]
        except RuntimeError:
            pass
    return _collect_all_files()


def _collect_all_files() -> list[Path]:
    files: list[Path] = []
    for directory in TARGET_DIRS:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file():
                files.append(path)
    return files


def _is_target_file(path: Path) -> bool:
    return path not in SKIP_FILES and path.suffix.lower() in {
        ".yml",
        ".yaml",
        ".js",
        ".ts",
        ".py",
    }


def _scan_file(path: Path) -> list[str]:
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [f"{path}: unable to read file"]

    violations: list[str] = []
    for pattern, label in DIRECT_PATTERNS:
        for match in pattern.finditer(content):
            line_no = content[: match.start()].count("\n") + 1
            violations.append(f"{path.relative_to(ROOT)}:{line_no}: {label}")

    has_api_calls = any(p.search(content) for p in API_CALL_PATTERNS)
    has_wrapper = any(hint in content for hint in WRAPPER_HINTS)

    if has_api_calls and not has_wrapper:
        for line_no, line in enumerate(content.splitlines(), start=1):
            if any(p.search(line) for p in API_CALL_PATTERNS):
                violations.append(
                    f"{path.relative_to(ROOT)}:{line_no}: API call without createTokenAwareRetry"
                )

    if (
        path.suffix.lower() in {".yml", ".yaml"}
        and has_api_calls
        and LOAD_BALANCER_HINT not in content
    ):
        violations.append(f"{path.relative_to(ROOT)}: missing export-load-balancer-tokens step")

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check for unwrapped GitHub API usage in workflows/scripts."
    )
    parser.add_argument("--base-ref", default=os.environ.get("GITHUB_BASE_REF", "main"))
    parser.add_argument("--base-remote", default=os.environ.get("BASE_REMOTE", "origin"))
    parser.add_argument("--all", action="store_true", help="Scan all files, not just diffs.")
    parser.add_argument("--output", help="Write report to the given file.")
    args = parser.parse_args()

    if args.all:
        candidates = _collect_all_files()
    else:
        candidates = _collect_changed_files(args.base_ref, args.base_remote)

    files = [path for path in candidates if _is_target_file(path)]

    if not files:
        if args.output:
            Path(args.output).write_text("No matching files to scan.\n", encoding="utf-8")
        return 0

    issues: list[str] = []
    for path in files:
        issues.extend(_scan_file(path))

    report_lines = []
    if issues:
        report_lines.append("API guard violations detected:\n")
        report_lines.extend(f"- {issue}" for issue in issues)
    else:
        report_lines.append("No API guard violations detected.")

    report = "\n".join(report_lines) + "\n"

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)

    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
