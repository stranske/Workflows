"""NDJSON parsing helpers with defensive error tracking."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def parse_ndjson_lines(
    lines: Iterable[str],
    *,
    source: str = "<memory>",
) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse NDJSON lines into a list of dicts and collect error messages."""
    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    for line_number, line in enumerate(lines, start=1):
        raw = line.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"{source}:{line_number}: invalid JSON ({exc.msg})")
            continue
        if isinstance(parsed, dict):
            entries.append(parsed)
        else:
            errors.append(f"{source}:{line_number}: expected object, got {type(parsed).__name__}")
    return entries, errors


def read_ndjson_file(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Read an NDJSON file and return entries plus any parsing errors."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], [f"{path}: {exc}"]
    return parse_ndjson_lines(content.splitlines(), source=str(path))
