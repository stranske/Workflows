#!/usr/bin/env python
"""Aggregate per-repo metrics NDJSON into org-level data."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_ndjson(path: Path) -> tuple[list[dict[str, Any]], int]:
    entries: list[dict[str, Any]] = []
    errors = 0
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return entries, 1
    for line in content.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            errors += 1
            continue
        if isinstance(parsed, dict):
            entries.append(parsed)
        else:
            errors += 1
    return entries, errors


def read_repo_metrics(path: Path, repo: str) -> tuple[list[dict[str, Any]], int]:
    """Load a per-repo metrics log and tag entries with the repo name."""
    entries, errors = _read_ndjson(path)
    tagged: list[dict[str, Any]] = []
    for entry in entries:
        tagged_entry = dict(entry)
        tagged_entry.setdefault("repo", repo)
        tagged.append(tagged_entry)
    return tagged, errors
