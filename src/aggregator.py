"""Aggregation helpers for repo metrics entries."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from src import percentile_calculator


def as_number(value: Any) -> float | None:
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


def infer_numeric_fields(entries: Iterable[dict[str, Any]]) -> list[str]:
    fields: set[str] = set()
    for entry in entries:
        for key, value in entry.items():
            if key == "repo":
                continue
            if as_number(value) is not None:
                fields.add(key)
    return sorted(fields)


def aggregate_numeric_fields(
    entries: Iterable[dict[str, Any]],
    fields: Iterable[str],
) -> dict[str, dict[str, float | None]]:
    aggregates: dict[str, dict[str, float | None]] = {}
    for field in fields:
        values: list[float] = []
        for entry in entries:
            value = as_number(entry.get(field))
            if value is not None:
                values.append(value)
        aggregates[field] = percentile_calculator.summarize_values(values)
    return aggregates


def group_entries(
    entries: Iterable[dict[str, Any]],
    keys: Iterable[str],
) -> dict[tuple[str, ...], list[dict[str, Any]]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    keys_list = list(keys)
    for entry in entries:
        group_key: list[str] = []
        for key in keys_list:
            value = entry.get(key)
            if value is None or value == "":
                group_key.append("unknown")
            else:
                group_key.append(str(value))
        group_tuple = tuple(group_key)
        grouped.setdefault(group_tuple, []).append(entry)
    return grouped


def build_grouped_aggregates(
    entries: Iterable[dict[str, Any]],
    numeric_fields: Iterable[str],
    group_keys: Iterable[str],
) -> list[dict[str, Any]]:
    aggregates: list[dict[str, Any]] = []
    grouped = group_entries(entries, group_keys)
    keys_list = list(group_keys)
    for group_values, group_entries_list in grouped.items():
        group_map = dict(zip(keys_list, group_values, strict=False))
        for field in numeric_fields:
            values = [
                as_number(entry.get(field))
                for entry in group_entries_list
                if as_number(entry.get(field)) is not None
            ]
            summary = percentile_calculator.summarize_values(values)
            aggregates.append(
                {
                    "entry_type": "aggregate",
                    "repo": "all",
                    "group": group_map,
                    "field": field,
                    "count": len(values),
                    "summary": summary,
                }
            )
    return aggregates
