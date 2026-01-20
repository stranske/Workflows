#!/usr/bin/env python3
"""Apply metrics retention policy to NDJSON logs and archive older data."""

from __future__ import annotations

import argparse
import calendar
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

DEFAULT_CONFIG_PATH = Path("config/retention-policy.json")
DEFAULT_RETENTION_LOG = Path("metrics-retention.ndjson")
DEFAULT_METRICS_PATHS = (
    "metrics-history.ndjson",
    "keepalive-metrics.ndjson",
    "workflow-metrics.ndjson",
    "autopilot-metrics.ndjson",
)
DEFAULT_METRICS_DIRS = ("agent-metrics",)
TIMESTAMP_FIELDS = (
    "timestamp",
    "created_at",
    "completed_at",
    "merged_at",
    "ended_at",
    "start_time",
)


@dataclass(frozen=True)
class RetentionPolicy:
    keep_days: int
    keep_weeks: int
    keep_months: int
    archive_enabled: bool
    archive_dir: Path


@dataclass
class FileRetentionStats:
    path: Path
    records_total: int = 0
    records_kept: int = 0
    records_archived_weekly: int = 0
    records_archived_monthly: int = 0
    records_purged: int = 0
    records_skipped: int = 0
    parse_errors: int = 0
    bytes_before: int = 0
    bytes_after: int = 0
    bytes_archived: int = 0

    def reduction_percent(self) -> float:
        if self.bytes_before <= 0:
            return 0.0
        reduced = max(self.bytes_before - self.bytes_after, 0)
        return (reduced / self.bytes_before) * 100.0


def _now_utc() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _parse_iso_timestamp(value: str) -> datetime | None:
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_timestamp_value(value: Any) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    return _parse_iso_timestamp(str(value))


def _extract_timestamp(record: dict[str, Any]) -> datetime | None:
    for field in TIMESTAMP_FIELDS:
        if field in record:
            return _parse_timestamp_value(record[field])
    return None


def _subtract_months(value: datetime, months: int) -> datetime:
    if months <= 0:
        return value
    year = value.year
    month = value.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _write_line(handle: Any, line: str) -> None:
    if line.endswith("\n"):
        handle.write(line)
    else:
        handle.write(line + "\n")


def _bucket_for_week(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}.ndjson"


def _bucket_for_month(dt: datetime) -> str:
    return f"{dt.year}-{dt.month:02d}.ndjson"


def _archive_path(archive_root: Path, source_path: Path, period: str, bucket: str) -> Path:
    base_name = source_path.stem
    return archive_root / base_name / period / bucket


def _iter_metrics_paths(
    metrics_paths: list[str],
    metrics_dirs: Iterable[str],
    log_path: Path,
) -> list[Path]:
    seen: set[Path] = set()
    candidates: list[Path] = []
    for path in metrics_paths:
        if not path:
            continue
        resolved = Path(path)
        if resolved not in seen:
            seen.add(resolved)
            candidates.append(resolved)

    for directory in metrics_dirs:
        root = Path(directory)
        if not root.is_dir():
            continue
        for entry in sorted(root.glob("*.ndjson")):
            if entry not in seen:
                seen.add(entry)
                candidates.append(entry)

    defaults = [Path(name) for name in DEFAULT_METRICS_PATHS]
    for entry in defaults:
        if entry not in seen:
            seen.add(entry)
            candidates.append(entry)

    return [path for path in candidates if path.exists() and path != log_path]


def load_policy(config_path: Path, archive_override: str | None = None) -> RetentionPolicy:
    if not config_path.is_file():
        raise FileNotFoundError(f"Retention config not found: {config_path}")
    data = json.loads(config_path.read_text(encoding="utf-8"))
    retention = data.get("retention", {})
    daily = retention.get("daily", {})
    weekly = retention.get("weekly", {})
    monthly = retention.get("monthly", {})
    archive = data.get("archive", {})
    keep_days = int(daily.get("keep_days", 14))
    keep_weeks = int(weekly.get("keep_weeks", 8))
    keep_months = int(monthly.get("keep_months", 24))
    archive_enabled = bool(archive.get("enabled", True))
    archive_dir = Path(archive_override or archive.get("storage_dir", "archives/metrics"))
    return RetentionPolicy(
        keep_days=keep_days,
        keep_weeks=keep_weeks,
        keep_months=keep_months,
        archive_enabled=archive_enabled,
        archive_dir=archive_dir,
    )


def apply_retention_to_file(
    path: Path,
    policy: RetentionPolicy,
    *,
    now: datetime,
    dry_run: bool,
) -> FileRetentionStats:
    stats = FileRetentionStats(path=path)
    if not path.exists():
        return stats
    stats.bytes_before = path.stat().st_size

    daily_cutoff = now - timedelta(days=policy.keep_days)
    weekly_cutoff = now - timedelta(weeks=policy.keep_weeks)
    monthly_cutoff = _subtract_months(now, policy.keep_months)

    temp_path = path.with_suffix(path.suffix + ".tmp")
    changed = False

    if dry_run:
        temp_handle = None
    else:
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_handle = temp_path.open("w", encoding="utf-8")

    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                stats.records_total += 1
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    stats.parse_errors += 1
                    stats.records_kept += 1
                    if temp_handle is not None:
                        _write_line(temp_handle, line)
                    continue

                timestamp = _extract_timestamp(record)
                if timestamp is None:
                    stats.records_skipped += 1
                    stats.records_kept += 1
                    if temp_handle is not None:
                        _write_line(temp_handle, line)
                    continue

                if timestamp >= daily_cutoff:
                    stats.records_kept += 1
                    if temp_handle is not None:
                        _write_line(temp_handle, line)
                    continue

                if not policy.archive_enabled:
                    stats.records_kept += 1
                    if temp_handle is not None:
                        _write_line(temp_handle, line)
                    continue

                if timestamp >= weekly_cutoff:
                    stats.records_archived_weekly += 1
                    changed = True
                    bucket = _bucket_for_week(timestamp)
                    archive_path = _archive_path(policy.archive_dir, path, "weekly", bucket)
                elif timestamp >= monthly_cutoff:
                    stats.records_archived_monthly += 1
                    changed = True
                    bucket = _bucket_for_month(timestamp)
                    archive_path = _archive_path(policy.archive_dir, path, "monthly", bucket)
                else:
                    stats.records_purged += 1
                    changed = True
                    continue

                if dry_run:
                    stats.bytes_archived += len(stripped) + 1
                    continue

                archive_path.parent.mkdir(parents=True, exist_ok=True)
                with archive_path.open("a", encoding="utf-8") as archive_handle:
                    _write_line(archive_handle, line)
                stats.bytes_archived += len(stripped) + 1

    finally:
        if temp_handle is not None:
            temp_handle.close()

    if dry_run:
        stats.bytes_after = stats.bytes_before
        if temp_path.exists():
            temp_path.unlink()
        return stats

    if changed:
        temp_path.replace(path)
    else:
        if temp_path.exists():
            temp_path.unlink()

    if path.exists():
        stats.bytes_after = path.stat().st_size
    return stats


def _build_log_record(
    stats: FileRetentionStats,
    *,
    timestamp: datetime,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "schema_version": 1,
        "component": "metrics_retention",
        "record_type": "retention_file",
        "path": str(stats.path),
        "records_total": stats.records_total,
        "records_kept": stats.records_kept,
        "records_archived_weekly": stats.records_archived_weekly,
        "records_archived_monthly": stats.records_archived_monthly,
        "records_purged": stats.records_purged,
        "records_skipped": stats.records_skipped,
        "parse_errors": stats.parse_errors,
        "bytes_before": stats.bytes_before,
        "bytes_after": stats.bytes_after,
        "bytes_archived": stats.bytes_archived,
        "reduction_percent": round(stats.reduction_percent(), 2),
        "dry_run": dry_run,
    }


def _append_log(log_path: Path, payload: dict[str, Any], *, dry_run: bool) -> None:
    if dry_run:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def restore_archive(
    archive_path: Path,
    output_path: Path,
    *,
    dedupe: bool,
    dry_run: bool,
) -> dict[str, Any]:
    if not archive_path.exists():
        raise FileNotFoundError(f"Archive path not found: {archive_path}")

    archive_files: list[Path] = []
    if archive_path.is_dir():
        archive_files = sorted(archive_path.rglob("*.ndjson"))
    else:
        archive_files = [archive_path]

    existing_lines: set[str] = set()
    if dedupe and output_path.exists():
        with output_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    existing_lines.add(stripped)

    restored = 0
    skipped = 0
    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_handle = output_path.open("a", encoding="utf-8")
    else:
        output_handle = None

    try:
        for path in archive_files:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if dedupe and stripped in existing_lines:
                        skipped += 1
                        continue
                    restored += 1
                    if dedupe:
                        existing_lines.add(stripped)
                    if output_handle is not None:
                        _write_line(output_handle, line)
    finally:
        if output_handle is not None:
            output_handle.close()

    return {
        "archive_path": str(archive_path),
        "output_path": str(output_path),
        "records_restored": restored,
        "records_skipped": skipped,
        "dry_run": dry_run,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply retention policy to metrics logs.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Retention config path")
    parser.add_argument(
        "--metrics-paths",
        help="Comma-separated NDJSON paths to process (defaults to known metrics files).",
    )
    parser.add_argument(
        "--metrics-dir",
        action="append",
        default=[],
        help="Directory to scan for NDJSON logs (can be provided multiple times).",
    )
    parser.add_argument("--archive-dir", help="Override archive storage directory")
    parser.add_argument("--log-path", default=str(DEFAULT_RETENTION_LOG), help="Retention log path")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    parser.add_argument("--restore", action="store_true", help="Restore from archived NDJSON")
    parser.add_argument("--archive-path", help="Archive file or directory to restore from")
    parser.add_argument("--output-path", help="Output NDJSON path for restore")
    parser.add_argument("--no-dedupe", action="store_true", help="Disable dedupe during restore")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    log_path = Path(args.log_path)
    now = _now_utc()

    if args.restore:
        if not args.archive_path or not args.output_path:
            parser.error("--restore requires --archive-path and --output-path")
        payload = restore_archive(
            Path(args.archive_path),
            Path(args.output_path),
            dedupe=not args.no_dedupe,
            dry_run=args.dry_run,
        )
        payload.update(
            {
                "timestamp": now.isoformat().replace("+00:00", "Z"),
                "schema_version": 1,
                "component": "metrics_retention",
                "record_type": "restore",
            }
        )
        _append_log(log_path, payload, dry_run=args.dry_run)
        print(
            "metrics_retention: restored",
            payload["records_restored"],
            "records from",
            payload["archive_path"],
        )
        return 0

    metrics_paths = []
    if args.metrics_paths:
        metrics_paths = [item.strip() for item in args.metrics_paths.split(",") if item.strip()]

    policy = load_policy(Path(args.config), archive_override=args.archive_dir)
    metrics_dirs = list(args.metrics_dir) + list(DEFAULT_METRICS_DIRS)
    targets = _iter_metrics_paths(metrics_paths, metrics_dirs, log_path)
    if not targets:
        print("metrics_retention: no metrics files found.", file=sys.stderr)
        return 1

    summary = {
        "files_processed": 0,
        "records_total": 0,
        "records_kept": 0,
        "records_archived_weekly": 0,
        "records_archived_monthly": 0,
        "records_purged": 0,
        "records_skipped": 0,
        "parse_errors": 0,
        "bytes_before": 0,
        "bytes_after": 0,
        "bytes_archived": 0,
    }

    for path in targets:
        stats = apply_retention_to_file(path, policy, now=now, dry_run=args.dry_run)
        summary["files_processed"] += 1
        summary["records_total"] += stats.records_total
        summary["records_kept"] += stats.records_kept
        summary["records_archived_weekly"] += stats.records_archived_weekly
        summary["records_archived_monthly"] += stats.records_archived_monthly
        summary["records_purged"] += stats.records_purged
        summary["records_skipped"] += stats.records_skipped
        summary["parse_errors"] += stats.parse_errors
        summary["bytes_before"] += stats.bytes_before
        summary["bytes_after"] += stats.bytes_after
        summary["bytes_archived"] += stats.bytes_archived
        payload = _build_log_record(stats, timestamp=now, dry_run=args.dry_run)
        _append_log(log_path, payload, dry_run=args.dry_run)

    reduced = max(summary["bytes_before"] - summary["bytes_after"], 0)
    reduction_percent = (reduced / summary["bytes_before"] * 100.0) if summary["bytes_before"] else 0.0
    summary_payload = {
        "timestamp": now.isoformat().replace("+00:00", "Z"),
        "schema_version": 1,
        "component": "metrics_retention",
        "record_type": "retention_summary",
        "dry_run": args.dry_run,
        "reduction_percent": round(reduction_percent, 2),
        **summary,
    }
    _append_log(log_path, summary_payload, dry_run=args.dry_run)

    print(
        "metrics_retention: processed",
        summary["files_processed"],
        "files; reduction",
        f"{summary_payload['reduction_percent']}%",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
