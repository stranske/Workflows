"""NDJSON parsing helpers with defensive error tracking."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

_MAX_LEGACY_JSON_FALLBACK_LINES = 5000
_MAX_LEGACY_JSON_FALLBACK_BYTES = 1024 * 1024


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
        handle = path.open("r", encoding="utf-8")
    except OSError as exc:
        return [], [f"{path}: {exc}"]

    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    raw_lines_for_fallback: list[str] = []
    raw_fallback_bytes = 0
    raw_fallback_truncated = False
    with handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            if not entries and not raw_fallback_truncated:
                raw_bytes = len(raw.encode("utf-8")) + 1
                fallback_within_limit = (
                    len(raw_lines_for_fallback) < _MAX_LEGACY_JSON_FALLBACK_LINES
                    and raw_fallback_bytes + raw_bytes <= _MAX_LEGACY_JSON_FALLBACK_BYTES
                )
                if fallback_within_limit:
                    raw_fallback_bytes += raw_bytes
                    raw_lines_for_fallback.append(raw)
                else:
                    raw_fallback_truncated = True
                    raw_lines_for_fallback = []
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                errors.append(f"{path}:{line_number}: invalid JSON ({exc.msg})")
                continue
            if isinstance(parsed, dict):
                entries.append(parsed)
                raw_lines_for_fallback = []
            else:
                errors.append(f"{path}:{line_number}: expected object, got {type(parsed).__name__}")

    if entries or not errors:
        return entries, errors

    raw_text = "\n".join(raw_lines_for_fallback)
    if raw_fallback_truncated:
        errors.append(f"{path}: legacy-json-fallback-buffer-limit")
        return entries, errors

    try:
        parsed_file = json.loads(raw_text)
    except json.JSONDecodeError:
        return entries, errors

    if isinstance(parsed_file, dict):
        return [parsed_file], []
    if isinstance(parsed_file, list) and all(isinstance(item, dict) for item in parsed_file):
        return list(parsed_file), []
    return entries, errors
