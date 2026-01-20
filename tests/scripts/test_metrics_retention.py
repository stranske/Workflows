from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts import metrics_retention


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("".join(lines), encoding="utf-8")


def _load_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_apply_retention_archives_and_purges(tmp_path: Path) -> None:
    now = metrics_retention._now_utc()
    metrics_path = tmp_path / "metrics-history.ndjson"
    archive_root = tmp_path / "archives"
    policy = metrics_retention.RetentionPolicy(
        keep_days=7,
        keep_weeks=4,
        keep_months=6,
        archive_enabled=True,
        archive_dir=archive_root,
    )

    recent = now - timedelta(days=1)
    weekly = now - timedelta(days=10)
    monthly = now - timedelta(days=40)
    purge = now - timedelta(days=300)
    lines = [
        f'{{"timestamp":"{recent.isoformat().replace("+00:00","Z")}","value":1}}\n',
        f'{{"timestamp":"{weekly.isoformat().replace("+00:00","Z")}","value":2}}\n',
        f'{{"timestamp":"{monthly.isoformat().replace("+00:00","Z")}","value":3}}\n',
        f'{{"timestamp":"{purge.isoformat().replace("+00:00","Z")}","value":4}}\n',
        '{"value":5}\n',
        '{"bad json"\n',
    ]
    _write_lines(metrics_path, lines)

    stats = metrics_retention.apply_retention_to_file(metrics_path, policy, now=now, dry_run=False)

    remaining = _load_lines(metrics_path)
    assert any('"value":1' in line for line in remaining)
    assert any('"value":5' in line for line in remaining)
    assert any('{"bad json"' in line for line in remaining)
    assert not any('"value":2' in line for line in remaining)
    assert not any('"value":3' in line for line in remaining)
    assert not any('"value":4' in line for line in remaining)

    weekly_bucket = metrics_retention._bucket_for_week(weekly)
    weekly_path = archive_root / "metrics-history" / "weekly" / weekly_bucket
    assert weekly_path.exists()
    weekly_lines = _load_lines(weekly_path)
    assert any('"value":2' in line for line in weekly_lines)

    monthly_bucket = metrics_retention._bucket_for_month(monthly)
    monthly_path = archive_root / "metrics-history" / "monthly" / monthly_bucket
    assert monthly_path.exists()
    monthly_lines = _load_lines(monthly_path)
    assert any('"value":3' in line for line in monthly_lines)

    assert stats.records_total == 6
    assert stats.records_kept == 3
    assert stats.records_archived_weekly == 1
    assert stats.records_archived_monthly == 1
    assert stats.records_purged == 1
    assert stats.records_skipped == 1
    assert stats.parse_errors == 1


def test_restore_archive_dedupes(tmp_path: Path) -> None:
    archive_path = tmp_path / "archives" / "metrics" / "weekly"
    archive_path.mkdir(parents=True, exist_ok=True)
    archive_file = archive_path / "2025-W01.ndjson"
    output_path = tmp_path / "metrics-history.ndjson"

    _write_lines(archive_file, ['{"timestamp":"2025-01-02T00:00:00Z","value":1}\n'])
    _write_lines(output_path, ['{"timestamp":"2025-01-02T00:00:00Z","value":1}\n'])

    result = metrics_retention.restore_archive(
        archive_file,
        output_path,
        dedupe=True,
        dry_run=False,
    )

    assert result["records_restored"] == 0
    assert result["records_skipped"] == 1
    restored = _load_lines(output_path)
    assert len(restored) == 1


def test_main_enforces_min_reduction_percent(tmp_path: Path) -> None:
    now = metrics_retention._now_utc()
    metrics_path = tmp_path / "metrics-history.ndjson"
    log_path = tmp_path / "metrics-retention.ndjson"
    config_path = tmp_path / "retention-policy.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "retention": {
                    "daily": {"keep_days": 1},
                    "weekly": {"keep_weeks": 1},
                    "monthly": {"keep_months": 1},
                },
                "archive": {"enabled": True, "storage_dir": str(tmp_path / "archives")},
            }
        ),
        encoding="utf-8",
    )

    recent = now - timedelta(hours=1)
    older = now - timedelta(days=10)
    lines = [f'{{"timestamp":"{recent.isoformat().replace("+00:00","Z")}","value":1}}\n']
    lines += [
        f'{{"timestamp":"{older.isoformat().replace("+00:00","Z")}","value":{idx}}}\n'
        for idx in range(2, 12)
    ]
    _write_lines(metrics_path, lines)

    exit_code = metrics_retention.main(
        [
            "--config",
            str(config_path),
            "--metrics-paths",
            str(metrics_path),
            "--log-path",
            str(log_path),
            "--min-reduction-percent",
            "50",
        ]
    )
    assert exit_code == 0

    metrics_path.write_text(
        f'{{"timestamp":"{recent.isoformat().replace("+00:00","Z")}","value":1}}\n'
        f'{{"timestamp":"{recent.isoformat().replace("+00:00","Z")}","value":2}}\n',
        encoding="utf-8",
    )
    exit_code = metrics_retention.main(
        [
            "--config",
            str(config_path),
            "--metrics-paths",
            str(metrics_path),
            "--log-path",
            str(log_path),
            "--min-reduction-percent",
            "50",
        ]
    )
    assert exit_code == 2
