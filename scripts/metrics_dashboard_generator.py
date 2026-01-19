#!/usr/bin/env python3
"""Generate a metrics dashboard from NDJSON logs."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

from scripts.aggregate_repo_metrics import summarize_values
from scripts.metrics_format_utils import ascii_sparkline, format_markdown_table

_DEFAULT_METRICS_PATH = "metrics-history.ndjson"
_DEFAULT_OUTPUT_PATH = "docs/metrics/WEEKLY_DASHBOARD.md"


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


def _status_from_threshold(
    value: float | None,
    ok_threshold: float,
    warn_threshold: float,
    *,
    higher_is_better: bool = True,
) -> str:
    if value is None:
        return "n/a"
    if higher_is_better:
        if value >= ok_threshold:
            return "OK"
        if value >= warn_threshold:
            return "WARN"
        return "FAIL"
    if value <= ok_threshold:
        return "OK"
    if value <= warn_threshold:
        return "WARN"
    return "FAIL"


def _status_for_field(
    field: str,
    latest_value: float | None,
    thresholds: dict[str, dict[str, Any]] | None,
) -> str:
    if not thresholds:
        return "n/a"
    rules = thresholds.get(field)
    if not rules:
        return "n/a"
    ok_threshold = _as_number(rules.get("ok"))
    warn_threshold = _as_number(rules.get("warn"))
    if ok_threshold is None or warn_threshold is None:
        return "n/a"
    higher_is_better = rules.get("higher_is_better", True)
    if not isinstance(higher_is_better, bool):
        higher_is_better = True
    return _status_from_threshold(
        latest_value,
        float(ok_threshold),
        float(warn_threshold),
        higher_is_better=higher_is_better,
    )


def _org_summary_table(
    entries: list[dict[str, Any]],
    fields: list[str],
    thresholds: dict[str, dict[str, Any]] | None,
) -> str:
    rows: list[list[object]] = []
    for field in fields:
        series = _collect_series(entries, field)
        summary = summarize_values(series)
        latest_value = series[-1] if series else None
        rows.append(
            [
                field,
                _format_metric_value(summary["mean"]),
                _format_metric_value(summary["p50"]),
                _format_metric_value(summary["p90"]),
                _format_metric_value(summary["p99"]),
                _format_trend(series),
                _status_for_field(field, latest_value, thresholds),
            ]
        )
    return format_markdown_table(
        ["Metric", "Mean", "P50", "P90", "P99", "Trend", "Status"],
        rows,
    )


def _repo_section(
    repo: str,
    entries: list[dict[str, Any]],
    fields: list[str],
    thresholds: dict[str, dict[str, Any]] | None,
) -> str:
    rows: list[list[object]] = []
    for field in fields:
        series = _collect_series(entries, field)
        summary = summarize_values(series)
        latest_value = series[-1] if series else None
        rows.append(
            [
                field,
                _format_metric_value(summary["mean"]),
                _format_metric_value(summary["p50"]),
                _format_metric_value(summary["p90"]),
                _format_metric_value(summary["p99"]),
                _format_trend(series),
                _status_for_field(field, latest_value, thresholds),
            ]
        )

    table = format_markdown_table(
        ["Metric", "Mean", "P50", "P90", "P99", "Trend", "Status"],
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
    thresholds: dict[str, dict[str, Any]] | None = None,
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

    lines.append(_org_summary_table(entries, fields, thresholds))
    lines.append("")
    lines.append(_repo_overview_table(grouped, fields))
    lines.append("")
    lines.append("## Repo Details")
    lines.append("")

    for repo in sorted(grouped):
        lines.append(_repo_section(repo, grouped[repo], fields, thresholds))

    return "\n".join(lines)


def build_dashboard_from_path(
    metrics_path: Path,
    numeric_fields: list[str] | None = None,
    thresholds: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, int]:
    entries, errors = _read_ndjson(metrics_path)
    return build_dashboard(entries, errors, numeric_fields, thresholds), errors


def _parse_field_list(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    fields: list[str] = []
    for value in values:
        for item in value.split(","):
            field = item.strip()
            if field:
                fields.append(field)
    return fields or None


def _load_config(config_path: Path | None) -> dict[str, Any]:
    if config_path is None:
        return {}
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a JSON object: {config_path}")
    return payload


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    validated: dict[str, Any] = {}
    allowed = {"metrics_path", "output_path", "numeric_fields", "thresholds"}
    extra_keys = set(config) - allowed
    if extra_keys:
        extras = ", ".join(sorted(extra_keys))
        raise ValueError(f"Unsupported config keys: {extras}")

    metrics_path = config.get("metrics_path")
    if metrics_path is not None:
        if not isinstance(metrics_path, str) or not metrics_path.strip():
            raise ValueError("metrics_path must be a non-empty string")
        validated["metrics_path"] = metrics_path.strip()

    output_path = config.get("output_path")
    if output_path is not None:
        if not isinstance(output_path, str) or not output_path.strip():
            raise ValueError("output_path must be a non-empty string")
        validated["output_path"] = output_path.strip()

    numeric_fields = config.get("numeric_fields")
    if numeric_fields is not None:
        if isinstance(numeric_fields, str):
            numeric_fields = _parse_field_list([numeric_fields])
        elif isinstance(numeric_fields, list):
            numeric_fields = [str(item).strip() for item in numeric_fields if str(item).strip()]
        else:
            raise ValueError("numeric_fields must be a list of strings or a string")
        validated["numeric_fields"] = numeric_fields or []

    thresholds = config.get("thresholds")
    if thresholds is not None:
        if not isinstance(thresholds, dict):
            raise ValueError("thresholds must be an object mapping metric names to thresholds")
        validated_thresholds: dict[str, dict[str, Any]] = {}
        for field, raw in thresholds.items():
            if not isinstance(field, str) or not field.strip():
                raise ValueError("thresholds keys must be non-empty strings")
            if not isinstance(raw, dict):
                raise ValueError(f"thresholds for {field} must be an object")
            ok_threshold = _as_number(raw.get("ok"))
            warn_threshold = _as_number(raw.get("warn"))
            if ok_threshold is None or warn_threshold is None:
                raise ValueError(f"thresholds for {field} must include ok and warn values")
            higher_is_better = raw.get("higher_is_better", True)
            if not isinstance(higher_is_better, bool):
                raise ValueError(f"thresholds for {field} higher_is_better must be boolean")
            if higher_is_better and ok_threshold < warn_threshold:
                raise ValueError(
                    f"thresholds for {field} must have ok >= warn when higher_is_better is true"
                )
            if not higher_is_better and ok_threshold > warn_threshold:
                raise ValueError(
                    f"thresholds for {field} must have ok <= warn when higher_is_better is false"
                )
            validated_thresholds[field.strip()] = {
                "ok": float(ok_threshold),
                "warn": float(warn_threshold),
                "higher_is_better": higher_is_better,
            }
        validated["thresholds"] = validated_thresholds

    return validated


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a weekly metrics dashboard from NDJSON logs."
    )
    parser.add_argument("--path", help="NDJSON metrics path")
    parser.add_argument("--output", help="Markdown output path")
    parser.add_argument(
        "--fields",
        nargs="*",
        help="Optional list of numeric fields to include (comma-separated or space-delimited).",
    )
    parser.add_argument("--config", help="Path to JSON config with defaults.")
    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    config: dict[str, Any] = {}
    if args.config:
        try:
            config = _validate_config(_load_config(Path(args.config)))
        except (OSError, ValueError) as exc:
            print(f"metrics_dashboard_generator: {exc}", file=sys.stderr)
            return 1

    metrics_path_value = args.path or config.get("metrics_path") or _DEFAULT_METRICS_PATH
    output_path_value = args.output or config.get("output_path") or _DEFAULT_OUTPUT_PATH
    fields = _parse_field_list(args.fields)
    if fields is None:
        fields = config.get("numeric_fields")
    thresholds = config.get("thresholds")

    metrics_path = Path(metrics_path_value)
    if not metrics_path.exists():
        print(
            f"metrics_dashboard_generator: metrics file not found: {metrics_path}",
            file=sys.stderr,
        )
        return 1

    dashboard, errors = build_dashboard_from_path(
        metrics_path, numeric_fields=fields, thresholds=thresholds
    )
    if errors:
        print(f"metrics_dashboard_generator: parse errors: {errors}", file=sys.stderr)

    output_path = Path(output_path_value)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(dashboard, encoding="utf-8")
    print(f"Wrote metrics dashboard to {output_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main(sys.argv[1:]))
