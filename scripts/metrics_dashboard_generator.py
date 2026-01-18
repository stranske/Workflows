#!/usr/bin/env python3
"""Generate a metrics dashboard from NDJSON logs."""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from scripts.aggregate_repo_metrics import summarize_values
from scripts.metrics_format_utils import ascii_sparkline, format_markdown_table


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


def _parse_timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            parsed = _dt.datetime.fromisoformat(raw)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_dt.UTC)
        return parsed.timestamp()
    return None


def _extract_timestamp(entry: dict[str, Any]) -> float | None:
    for key in ("timestamp", "recorded_at", "created_at", "time", "run_started_at"):
        timestamp = _parse_timestamp(entry.get(key))
        if timestamp is not None:
            return timestamp
    return None


def _infer_numeric_fields(entries: list[dict[str, Any]]) -> list[str]:
    fields: set[str] = set()
    for entry in entries:
        for key, value in entry.items():
            if key == "repo":
                continue
            if _as_number(value) is not None:
                fields.add(key)
    return sorted(fields)


def _group_by_repo(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        repo = entry.get("repo") or "unknown"
        repo_key = str(repo)
        grouped.setdefault(repo_key, []).append(entry)
    return grouped


def _collect_series(entries: list[dict[str, Any]], field: str) -> list[float]:
    points: list[tuple[float, float]] = []
    for idx, entry in enumerate(entries):
        value = _as_number(entry.get(field))
        if value is None:
            continue
        timestamp = _extract_timestamp(entry)
        if timestamp is None:
            timestamp = float(idx)
        points.append((timestamp, value))
    points.sort(key=lambda item: item[0])
    return [value for _, value in points]


def _format_metric_value(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _format_trend(series: list[float]) -> str:
    if len(series) < 2:
        return "n/a"
    return f"`{ascii_sparkline(series)}`"


def _format_timestamp(timestamp: float | None) -> str:
    if timestamp is None:
        return "n/a"
    return _dt.datetime.fromtimestamp(timestamp, tz=_dt.UTC).isoformat().replace("+00:00", "Z")


def _latest_timestamp(entries: list[dict[str, Any]]) -> float | None:
    timestamps = [_extract_timestamp(entry) for entry in entries]
    values = [timestamp for timestamp in timestamps if timestamp is not None]
    if not values:
        return None
    return max(values)


def _count_numeric_fields(entries: list[dict[str, Any]], fields: list[str]) -> int:
    count = 0
    for field in fields:
        if any(_as_number(entry.get(field)) is not None for entry in entries):
            count += 1
    return count


def _repo_overview_table(grouped: dict[str, list[dict[str, Any]]], fields: list[str]) -> str:
    rows: list[list[object]] = []
    for repo in sorted(grouped):
        entries = grouped[repo]
        rows.append(
            [
                repo,
                len(entries),
                _count_numeric_fields(entries, fields),
                _format_timestamp(_latest_timestamp(entries)),
            ]
        )
    return format_markdown_table(
        ["Repo", "Entries", "Metrics tracked", "Last update"],
        rows,
        alignments=["left", "right", "right", "left"],
    )


def _org_summary_table(entries: list[dict[str, Any]], fields: list[str]) -> str:
    rows: list[list[object]] = []
    for field in fields:
        series = _collect_series(entries, field)
        summary = summarize_values(series)
        rows.append(
            [
                field,
                _format_metric_value(summary["mean"]),
                _format_metric_value(summary["p50"]),
                _format_metric_value(summary["p90"]),
                _format_metric_value(summary["p99"]),
                _format_trend(series),
            ]
        )
    return format_markdown_table(
        ["Metric", "Mean", "P50", "P90", "P99", "Trend"],
        rows,
    )


def _repo_section(repo: str, entries: list[dict[str, Any]], fields: list[str]) -> str:
    rows: list[list[object]] = []
    for field in fields:
        series = _collect_series(entries, field)
        summary = summarize_values(series)
        rows.append(
            [
                field,
                _format_metric_value(summary["mean"]),
                _format_metric_value(summary["p50"]),
                _format_metric_value(summary["p90"]),
                _format_metric_value(summary["p99"]),
                _format_trend(series),
            ]
        )

    table = format_markdown_table(
        ["Metric", "Mean", "P50", "P90", "P99", "Trend"],
        rows,
    )
    return "\n".join(
        [
            f"### {repo}",
            "",
            f"Entries: {len(entries)}",
            "",
            table,
            "",
        ]
    )


def build_dashboard(
    entries: list[dict[str, Any]],
    errors: int,
    numeric_fields: list[str] | None = None,
) -> str:
    fields = numeric_fields or _infer_numeric_fields(entries)
    grouped = _group_by_repo(entries)
    now = _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    lines = [
        "# Weekly Metrics Dashboard",
        "",
        f"Generated: {now}",
        f"Total entries: {len(entries)}",
        f"Parse errors: {errors}",
        "",
        "## Org Summary",
        "",
        "## Per-Repo Summary",
        "",
    ]

    if not grouped:
        lines.append("No repo metrics found.")
        lines.append("")
        return "\n".join(lines)

    if not fields:
        lines.append("No numeric metrics found.")
        lines.append("")
        return "\n".join(lines)

    lines.append(_org_summary_table(entries, fields))
    lines.append("")
    lines.append(_repo_overview_table(grouped, fields))
    lines.append("")
    lines.append("## Repo Details")
    lines.append("")

    for repo in sorted(grouped):
        lines.append(_repo_section(repo, grouped[repo], fields))

    return "\n".join(lines)


def build_dashboard_from_path(
    metrics_path: Path,
    numeric_fields: list[str] | None = None,
) -> tuple[str, int]:
    entries, errors = _read_ndjson(metrics_path)
    return build_dashboard(entries, errors, numeric_fields), errors
