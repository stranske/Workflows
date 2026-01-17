#!/usr/bin/env python
"""Aggregate per-repo metrics NDJSON into org-level data."""
from __future__ import annotations

import json
import math
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


def _as_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def _percentile(sorted_values: list[float], percentile: float) -> float | None:
    if not sorted_values:
        return None
    if percentile <= 0:
        return sorted_values[0]
    if percentile >= 100:
        return sorted_values[-1]
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (percentile / 100) * (len(sorted_values) - 1)
    lower_index = int(math.floor(rank))
    upper_index = int(math.ceil(rank))
    if lower_index == upper_index:
        return sorted_values[lower_index]
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    weight = rank - lower_index
    return lower_value + (upper_value - lower_value) * weight


def summarize_values(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "p50": None, "p90": None, "p99": None}
    sorted_values = sorted(values)
    mean_value = sum(sorted_values) / len(sorted_values)
    return {
        "mean": mean_value,
        "p50": _percentile(sorted_values, 50),
        "p90": _percentile(sorted_values, 90),
        "p99": _percentile(sorted_values, 99),
    }


def aggregate_numeric_fields(
    entries: list[dict[str, Any]],
    fields: list[str],
) -> dict[str, dict[str, float | None]]:
    aggregates: dict[str, dict[str, float | None]] = {}
    for field in fields:
        values: list[float] = []
        for entry in entries:
            value = _as_number(entry.get(field))
            if value is not None:
                values.append(value)
        aggregates[field] = summarize_values(values)
    return aggregates
