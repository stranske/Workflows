#!/usr/bin/env python3
"""Validate Codex ledger files for durable progress tracking.

This script scans `.agents/issue-*-ledger.yml` files and verifies that they
conform to the expected minimal schema.  CI runs it to catch schema drift and
invalid status transitions.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if SRC_ROOT.exists():  # ensure local package import works before editable install
    sys.path.insert(0, str(SRC_ROOT))

try:  # pragma: no cover - exercised in worker runtime, mocked in tests
    from utils.paths import proj_path  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover - fallback for repo scripts

    def proj_path() -> Path:
        return REPO_ROOT


VALID_STATUSES = {"todo", "doing", "done"}
HEX_RE = re.compile(r"^[0-9a-f]{7,40}$")
ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SHALLOW_CACHE: bool | None = None

# Caches to avoid redundant git subprocess calls for the same commit.
_COMMIT_FILES_CACHE: dict[str, list[str]] = {}
_COMMIT_SUBJECT_CACHE: dict[str, str] = {}
_COMMIT_FETCH_CACHE: dict[str, bool] = {}  # SHA -> fetch succeeded


def _is_shallow_repo() -> bool:
    global _SHALLOW_CACHE
    if _SHALLOW_CACHE is not None:
        return _SHALLOW_CACHE
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "--is-shallow-repository"],
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        _SHALLOW_CACHE = False
        return _SHALLOW_CACHE
    _SHALLOW_CACHE = output.lower() == "true"
    return _SHALLOW_CACHE


def _allow_missing_commit() -> bool:
    if os.environ.get("LEDGER_VALIDATE_STRICT") == "1":
        return False
    if os.environ.get("LEDGER_VALIDATE_ALLOW_SHALLOW") == "1":
        return True
    if not os.environ.get("GITHUB_ACTIONS"):
        return False
    if _is_shallow_repo():
        return True
    # Allow missing commits on pull_request workflows where the fork/head history
    # may be incomplete or inaccessible to the runner token.
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    return event_name in {"pull_request", "pull_request_target"}


def _warn_skip_commit(commit: str, reason: str) -> None:
    print(
        f"Skipping commit validation for {commit}: {reason}",
        file=sys.stderr,
    )


class LedgerError(Exception):
    """Collect validation errors for reporting."""

    def __init__(self, message: str, *, context: str | None = None) -> None:
        super().__init__(message)
        self.context = context


def _load_yaml(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise LedgerError(f"invalid YAML: {exc}", context=str(path)) from exc


def _ensure_type(value: Any, expected: type, *, allow_none: bool = False) -> bool:
    if value is None and allow_none:
        return True
    return isinstance(value, expected)


def _validate_timestamp(value: Any, *, field: str, path: str) -> list[str]:
    errors: list[str] = []
    if value is None:
        return errors
    if not isinstance(value, str):
        errors.append(f"{path}.{field} must be a string or null")
        return errors
    if not ISO8601_RE.match(value):
        errors.append(f"{path}.{field} must be an ISO-8601 UTC timestamp (YYYY-MM-DDTHH:MM:SSZ)")
        return errors
    try:
        _dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        errors.append(f"{path}.{field} is not a valid timestamp: {exc}")
    return errors


def _pull_request_head_repo_url() -> str | None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return None
    try:
        with open(event_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    pull_request = payload.get("pull_request")
    if not isinstance(pull_request, dict):
        return None
    head = pull_request.get("head")
    if not isinstance(head, dict):
        return None
    repo = head.get("repo")
    if not isinstance(repo, dict):
        return None
    clone_url = repo.get("clone_url") or repo.get("git_url") or repo.get("ssh_url")
    if not isinstance(clone_url, str) or not clone_url.strip():
        full_name = repo.get("full_name")
        if isinstance(full_name, str) and full_name.strip():
            server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
            clone_url = f"{server}/{full_name}.git"
        else:
            return None
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        clone_url = _with_auth_token(clone_url, token)
    return clone_url


def _commit_exists_locally(commit: str) -> bool:
    """Fast check whether *commit* is known to the local object store."""
    try:
        kind = subprocess.check_output(
            ["git", "cat-file", "-t", commit],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return kind == "commit"
    except subprocess.CalledProcessError:
        return False


def _bulk_check_commits(shas: Iterable[str]) -> dict[str, bool]:
    """Batch-check which SHAs exist locally using `git cat-file --batch-check`."""
    unique = sorted(set(shas))
    if not unique:
        return {}
    try:
        proc = subprocess.run(
            ["git", "cat-file", "--batch-check"],
            input="\n".join(unique) + "\n",
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return dict.fromkeys(unique, False)
    # Map original input SHAs to results (handle abbreviated SHA -> full SHA expansion)
    # git cat-file --batch-check outputs lines in the same order as input
    results: dict[str, bool] = {}
    output_lines = proc.stdout.splitlines()
    for original_sha, line in zip(unique, output_lines, strict=False):
        parts = line.split()
        if len(parts) >= 2:
            # Use original_sha as key (not parts[0] which may be expanded)
            results[original_sha] = parts[1] == "commit"
        else:
            results[original_sha] = False
    # Handle any SHAs that didn't get a response line
    for sha in unique:
        results.setdefault(sha, False)
    return results


def _prefetch_commits(ledgers: list[Path]) -> None:
    """Collect all unique commit SHAs from ledgers and pre-fetch missing ones.

    This avoids O(tasks) individual `git show` + `_fetch_commit` invocations
    by doing a single bulk existence check followed by one fetch per unique
    missing commit.
    """
    all_shas: set[str] = set()
    for path in ledgers:
        try:
            data = _load_yaml(path)
        except LedgerError:
            continue
        if not isinstance(data, dict):
            continue
        tasks = data.get("tasks")
        if not isinstance(tasks, list):
            continue
        for task in tasks:
            if not isinstance(task, dict):
                continue
            commit = task.get("commit", "")
            if isinstance(commit, str) and HEX_RE.match(commit.lower()):
                all_shas.add(commit)

    if not all_shas:
        return

    # Bulk-check which commits are already available locally.
    presence = _bulk_check_commits(all_shas)
    missing = [sha for sha, exists in presence.items() if not exists]
    if not missing:
        return

    # Fetch all missing commits in as few operations as possible.
    for sha in missing:
        _fetch_commit(sha)


def _fetch_commit(commit: str) -> bool:
    """Ensure *commit* exists locally, fetching extra history if needed."""
    if commit in _COMMIT_FETCH_CACHE:
        return _COMMIT_FETCH_CACHE[commit]

    # Quick local check first — avoid network calls entirely.
    if _commit_exists_locally(commit):
        _COMMIT_FETCH_CACHE[commit] = True
        return True

    fetch_targets = ["origin"]
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo:
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
        base_url = f"{server}/{repo}.git"
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            base_url = _with_auth_token(base_url, token)
        if base_url not in fetch_targets:
            fetch_targets.append(base_url)
    pr_head_url = _pull_request_head_repo_url()
    if pr_head_url and pr_head_url not in fetch_targets:
        fetch_targets.append(pr_head_url)

    for target in fetch_targets:
        fetch_attempts = [
            [
                "git",
                "fetch",
                "--no-tags",
                "--filter=blob:none",
                target,
                commit,
            ],
            [
                "git",
                "fetch",
                "--no-tags",
                "--filter=blob:none",
                "--deepen",
                "256",
                target,
            ],
            [
                "git",
                "fetch",
                "--no-tags",
                "--filter=blob:none",
                "--unshallow",
                target,
            ],
            [
                "git",
                "fetch",
                "--no-tags",
                target,
                commit,
            ],
            [
                "git",
                "fetch",
                "--no-tags",
                target,
            ],
        ]

        for command in fetch_attempts:
            try:
                subprocess.check_call(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                continue

            if command[-1] == commit:
                _COMMIT_FETCH_CACHE[commit] = True
                return True

            # Success without specifying the SHA just deepened the local clone;
            # try once more to pull the exact commit while the additional history
            # is available.
            try:
                subprocess.check_call(
                    [
                        "git",
                        "fetch",
                        "--no-tags",
                        "--filter=blob:none",
                        target,
                        commit,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                continue
            _COMMIT_FETCH_CACHE[commit] = True
            return True

    _COMMIT_FETCH_CACHE[commit] = False
    return False


def _with_auth_token(base_url: str, token: str) -> str:
    """Embed a GitHub token into https URLs without logging it."""
    split = urlsplit(base_url)
    if split.scheme not in {"http", "https"} or not split.netloc:
        return base_url
    if "@" in split.netloc:
        return base_url
    authed_netloc = f"x-access-token:{token}@{split.netloc}"
    return urlunsplit((split.scheme, authed_netloc, split.path, split.query, split.fragment))


def _commit_files(commit: str) -> list[str]:
    if commit in _COMMIT_FILES_CACHE:
        return _COMMIT_FILES_CACHE[commit]
    try:
        output = subprocess.check_output(
            ["git", "show", "--pretty=format:", "--name-only", commit],
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        if _fetch_commit(commit):
            output = subprocess.check_output(
                ["git", "show", "--pretty=format:", "--name-only", commit],
                text=True,
            )
        else:
            raise LedgerError(f"unknown commit {commit}") from exc

    stripped_lines = (line.strip() for line in output.splitlines())
    files = [line for line in stripped_lines if line]
    _COMMIT_FILES_CACHE[commit] = files
    return files


def _commit_subject(commit: str) -> str:
    if commit in _COMMIT_SUBJECT_CACHE:
        return _COMMIT_SUBJECT_CACHE[commit]
    try:
        output = subprocess.check_output(
            ["git", "show", "--no-patch", "--pretty=format:%s", commit],
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        if _fetch_commit(commit):
            output = subprocess.check_output(
                ["git", "show", "--no-patch", "--pretty=format:%s", commit],
                text=True,
            )
        else:
            raise LedgerError(f"unknown commit {commit}") from exc
    result = output.strip()
    _COMMIT_SUBJECT_CACHE[commit] = result
    return result


def _validate_task(
    task: dict[str, Any], *, index: int, seen_ids: set[str], ledger_path: Path
) -> list[str]:
    errors: list[str] = []
    context = f"tasks[{index}]"

    task_id = task.get("id")
    if not isinstance(task_id, str) or not task_id.strip():
        errors.append(f"{context}.id must be a non-empty string")
    elif task_id in seen_ids:
        errors.append(f"duplicate task id: {task_id}")
    else:
        seen_ids.add(task_id)

    title = task.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append(f"{context}.title must be a non-empty string")

    status = task.get("status")
    if status not in VALID_STATUSES:
        errors.append(f"{context}.status must be one of {sorted(VALID_STATUSES)}")

    notes = task.get("notes", [])
    if notes is None:
        notes = []
        task["notes"] = notes
    if not isinstance(notes, list) or not all(isinstance(item, str) for item in notes):
        errors.append(f"{context}.notes must be a list of strings")

    errors.extend(_validate_timestamp(task.get("started_at"), field="started_at", path=context))
    errors.extend(_validate_timestamp(task.get("finished_at"), field="finished_at", path=context))

    commit = task.get("commit", "")
    if commit is None:
        commit = ""
        task["commit"] = commit
    if not isinstance(commit, str):
        errors.append(f"{context}.commit must be a string")
    else:
        if status == "done":
            if not commit:
                errors.append(f"{context}.commit is required when status is done")
            elif not HEX_RE.match(commit.lower()):
                errors.append(f"{context}.commit must be a Git SHA (7-40 hex characters)")
            else:
                try:
                    files = _commit_files(commit)
                except LedgerError as exc:
                    if _allow_missing_commit():
                        _warn_skip_commit(commit, str(exc))
                        return errors
                    errors.append(
                        f"{ledger_path}: {context}.commit {commit} not found in repository: {exc}"
                    )
                else:
                    if not files:
                        errors.append(
                            f"{ledger_path}: {context}.commit {commit} has no changed files"
                        )
                    else:
                        try:
                            ledger_relative = ledger_path.relative_to(REPO_ROOT).as_posix()
                        except ValueError:
                            ledger_relative = ledger_path.as_posix()

                        if all(name.startswith(".agents/") for name in files):
                            allowed_sidecars = {
                                ledger_relative,
                                ".agents/.ledger-summary.md",
                                ".agents/.ledger-start.json",
                            }
                            extra_files = [name for name in files if name not in allowed_sidecars]

                            try:
                                subject = _commit_subject(commit)
                            except LedgerError as exc:
                                if _allow_missing_commit():
                                    _warn_skip_commit(commit, str(exc))
                                    return errors
                                errors.append(
                                    f"{ledger_path}: {context}.commit {commit} not found in repository: {exc}"
                                )
                                subject = ""

                            if (
                                extra_files
                                or ledger_relative not in files
                                or not subject.lower().startswith("chore(ledger):")
                            ):
                                errors.append(
                                    f"{ledger_path}: {context}.commit {commit} must include non-ledger changes"
                                )
        else:
            if commit and not HEX_RE.match(commit.lower()):
                errors.append(f"{context}.commit must be empty or a Git SHA")

    if status != "done" and task.get("finished_at"):
        errors.append(f"{context}.finished_at must be null unless status is done")
    if status == "todo" and task.get("started_at"):
        errors.append(f"{context}.started_at must be null when status is todo")

    return errors


def validate_ledger(path: Path) -> list[str]:
    problems: list[str] = []
    data = _load_yaml(path)
    if not isinstance(data, dict):
        return [f"{path}: top-level document must be a mapping"]

    version = data.get("version")
    if version != 1:
        problems.append(f"{path}: version must be 1")

    issue = data.get("issue")
    if not isinstance(issue, int):
        problems.append(f"{path}: issue must be an integer")

    base = data.get("base")
    if not isinstance(base, str) or not base.strip():
        problems.append(f"{path}: base must be a non-empty string")

    branch = data.get("branch")
    if not isinstance(branch, str) or not branch.strip():
        problems.append(f"{path}: branch must be a non-empty string")

    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        problems.append(f"{path}: tasks must be a non-empty list")
        return problems

    seen_ids: set[str] = set()
    doing_count = 0
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            problems.append(f"{path}: tasks[{index}] must be a mapping")
            continue
        problems.extend(_validate_task(task, index=index, seen_ids=seen_ids, ledger_path=path))
        if task.get("status") == "doing":
            doing_count += 1

    if doing_count > 1:
        problems.append(f"{path}: at most one task may have status=doing (found {doing_count})")

    return problems


def find_ledgers(explicit: Iterable[str]) -> list[Path]:
    if explicit:
        return [Path(item) for item in explicit]
    root = proj_path()
    agents_dir = root / ".agents"
    if not agents_dir.exists():
        return []
    return sorted(agents_dir.glob("issue-*-ledger.yml"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Codex ledger files")
    parser.add_argument(
        "paths",
        metavar="PATH",
        nargs="*",
        help="Specific ledger files to validate (defaults to .agents/issue-*-ledger.yml)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit validation report as JSON (useful for tooling)",
    )
    args = parser.parse_args(argv)

    ledgers = find_ledgers(args.paths)

    # Pre-fetch all unique commits in bulk to avoid O(tasks) individual fetches.
    _prefetch_commits(ledgers)

    results: dict[str, list[str]] = {}
    for path in ledgers:
        problems = validate_ledger(path)
        if problems:
            results[str(path)] = problems

    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        if not ledgers:
            print("No ledger files found.")
        for ledger_key, problems in results.items():  # noqa: B007
            for problem in problems:
                print(problem, file=sys.stderr)
        if not results and ledgers:
            for path in ledgers:
                print(f"Validated {path}")

    return 1 if results else 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
