#!/usr/bin/env python3
"""Evidence checks for Codex belt ledger task completion."""

from __future__ import annotations

import re
import subprocess
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any

_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_LINE_SUFFIX_RE = re.compile(r":\d+(?:-\d+)?$")
_STATUS_KEYS = ("todo", "in_progress", "done", "blocked")
_FILE_SUFFIXES = {
    ".cfg",
    ".css",
    ".csv",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}


class CompletionEvidenceError(RuntimeError):
    """Raised when Git evidence cannot be read safely."""


def task_artifacts(task: dict[str, Any]) -> list[str]:
    """Extract conservative repository artifact paths from a task title."""
    title = str(task.get("title") or "")
    artifacts: list[str] = []
    for match in _BACKTICK_RE.finditer(title):
        token = _LINE_SUFFIX_RE.sub("", match.group(1).strip()).removeprefix("./")
        if not token or any(char.isspace() for char in token):
            continue
        if token.startswith(("--", "http://", "https://", "stranske/")):
            continue
        if "::" in token or any(char in token for char in "()"):
            continue
        path = PurePosixPath(token)
        if path.is_absolute() or ".." in path.parts:
            continue
        # Schema identifiers such as tracked-variable/v1 are not paths. Require
        # a file-like final component; extensionless paths remain opt-in rather
        # than silently blocking a valid task.
        if path.suffix.lower() not in _FILE_SUFFIXES:
            continue
        if token not in artifacts:
            artifacts.append(token)
    return artifacts


def commit_files(commit: str, *, repo_root: Path | str = ".") -> list[str]:
    """Return paths changed by *commit*, including root commits."""
    command = [
        "git",
        "-C",
        str(repo_root),
        "show",
        "--pretty=format:",
        "--name-only",
        "--diff-merges=first-parent",
        "-z",
        commit,
    ]
    try:
        output = subprocess.check_output(command, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as exc:
        raise CompletionEvidenceError(f"commit {commit} is unavailable") from exc
    return [item.decode("utf-8", "surrogateescape") for item in output.split(b"\0") if item]


def commit_has_path(commit: str, path: str, *, repo_root: Path | str = ".") -> bool:
    """Return whether *path* exists in the tree recorded by *commit*."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "cat-file", "-e", f"{commit}:{path}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def completion_errors(
    task: dict[str, Any],
    commit: str,
    *,
    repo_root: Path | str = ".",
) -> list[str]:
    """Return reasons why *task* cannot transition to ``done`` at *commit*."""
    task_id = str(task.get("id") or "<unknown>")
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", commit):
        return [f"task {task_id} cites invalid commit {commit or '<empty>'}"]
    try:
        files = commit_files(commit, repo_root=repo_root)
    except CompletionEvidenceError as exc:
        return [f"task {task_id} cannot verify commit {commit}: {exc}"]
    substantive = [path for path in files if not path.startswith(".agents/")]
    errors: list[str] = []
    if not substantive:
        errors.append(f"task {task_id} commit {commit} changes only ledger paths")
    missing = [
        path
        for path in task_artifacts(task)
        if not commit_has_path(commit, path, repo_root=repo_root)
    ]
    if missing:
        errors.append(
            f"task {task_id} commit {commit} is missing named artifact(s): {', '.join(missing)}"
        )
    return errors


def _commits_after(start_sha: str, end_sha: str, *, repo_root: Path | str) -> list[str]:
    """Return commits reachable from end_sha but not start_sha, oldest first."""
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", start_sha) or not re.fullmatch(
        r"[0-9a-fA-F]{7,40}", end_sha
    ):
        return []
    try:
        output = subprocess.check_output(
            [
                "git",
                "-C",
                str(repo_root),
                "rev-list",
                "--reverse",
                f"{start_sha}..{end_sha}",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except subprocess.CalledProcessError:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def resolve_completion_commit(
    task: dict[str, Any],
    start_sha: str | None,
    end_sha: str,
    *,
    repo_root: Path | str = ".",
) -> tuple[str | None, list[str]]:
    """Pick the commit that may complete *task*, or defer if the agent has not landed yet."""
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", end_sha):
        return None, [
            f"task {task.get('id') or '<unknown>'} cites invalid head {end_sha or '<empty>'}"
        ]

    if not start_sha:
        blockers = completion_errors(task, end_sha, repo_root=repo_root)
        if blockers and all("changes only ledger paths" in item for item in blockers):
            return None, []
        return end_sha, blockers

    candidates = _commits_after(start_sha, end_sha, repo_root=repo_root)
    substantive = [
        commit
        for commit in candidates
        if any(
            not path.startswith(".agents/") for path in commit_files(commit, repo_root=repo_root)
        )
    ]
    if not substantive:
        return None, []

    for commit in reversed(substantive):
        blockers = completion_errors(task, commit, repo_root=repo_root)
        if not blockers:
            return commit, []
        if not all("changes only ledger paths" in item for item in blockers):
            return commit, blockers

    return None, []


def duplicate_artifact_errors(
    tasks: Iterable[dict[str, Any]], *, repo_root: Path | str = "."
) -> list[str]:
    """Flag duplicate artifact claims whose completed task lacks the artifact."""
    references: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        if not isinstance(task, dict):
            continue
        for path in task_artifacts(task):
            references[path].append(task)

    errors: list[str] = []
    for path, path_tasks in references.items():
        if len(path_tasks) < 2:
            continue
        task_ids = ", ".join(str(task.get("id") or "<unknown>") for task in path_tasks)
        for task in path_tasks:
            if task.get("status") != "done":
                continue
            commit = str(task.get("commit") or "")
            if not commit or not commit_has_path(commit, path, repo_root=repo_root):
                errors.append(
                    f"duplicate artifact {path} is claimed by {task_ids}, but done task "
                    f"{task.get('id') or '<unknown>'} lacks it at commit {commit or '<empty>'}"
                )
    return errors


def status_counts(tasks: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Return the four operator-facing task counts, including zeros."""
    raw = Counter(str(task.get("status") or "") for task in tasks if isinstance(task, dict))
    counts = {
        "todo": raw["todo"],
        "in_progress": raw["doing"],
        "done": raw["done"],
        "blocked": raw["blocked"],
    }
    return {key: counts[key] for key in _STATUS_KEYS}


def format_status_counts(tasks: Iterable[dict[str, Any]]) -> str:
    counts = status_counts(tasks)
    return "Belt task counts: " + " ".join(f"{key}={counts[key]}" for key in _STATUS_KEYS)
