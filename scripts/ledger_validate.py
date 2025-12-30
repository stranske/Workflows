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
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if SRC_ROOT.exists():  # ensure local package import works before editable install
    sys.path.insert(0, str(SRC_ROOT))

from utils.paths import proj_path  # noqa: E402

VALID_STATUSES = {"todo", "doing", "done"}
HEX_RE = re.compile(r"^[0-9a-f]{7,40}$")
ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


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


def _fetch_commit(commit: str) -> bool:
    """Ensure *commit* exists locally, fetching extra history if needed."""

    fetch_attempts = [
        [
            "git",
            "fetch",
            "--no-tags",
            "--filter=blob:none",
            "origin",
            commit,
        ],
        [
            "git",
            "fetch",
            "--no-tags",
            "--filter=blob:none",
            "--deepen",
            "256",
            "origin",
        ],
        [
            "git",
            "fetch",
            "--no-tags",
            "--filter=blob:none",
            "--unshallow",
            "origin",
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
                    "origin",
                    commit,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            continue
        return True

    return False


def _commit_files(commit: str) -> list[str]:
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
    return files


def _commit_subject(commit: str) -> str:
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
    return output.strip()


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
