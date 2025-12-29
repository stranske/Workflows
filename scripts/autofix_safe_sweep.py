"""Helpers for autofix safe-sweep path handling."""
from __future__ import annotations

from collections.abc import Iterable
import fnmatch


def _normalise_dir(path: str) -> str:
    if not path:
        return ""
    cleaned = path.rstrip("/")
    if cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned or "."


def filter_parent_dirs(paths: Iterable[str]) -> list[str]:
    """Drop subdirectories when a parent directory is already selected."""
    filtered: list[str] = []
    for raw in paths:
        cleaned = _normalise_dir(raw)
        if not cleaned:
            continue
        is_subdir = False
        for parent in filtered:
            if cleaned != parent and cleaned.startswith(f"{parent.rstrip('/')}/"):
                is_subdir = True
                break
        if not is_subdir:
            filtered.append(cleaned)
    return filtered


def dir_to_glob(path: str) -> str:
    """Convert a directory path into a glob pattern for bash-style matching."""
    cleaned = _normalise_dir(path)
    if cleaned in ("", "."):
        return "**"
    return f"{cleaned}/**"


def build_allowed_globs(directories: Iterable[str]) -> list[str]:
    filtered = filter_parent_dirs(directories)
    patterns = [dir_to_glob(path) for path in filtered]
    return patterns or ["**/*.py"]


def matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)
