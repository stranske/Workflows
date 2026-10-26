from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
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
        f'{{"timestamp":"{recent.isoformat().replace("+00:00", "Z")}","value":1}}\n',
        f'{{"timestamp":"{weekly.isoformat().replace("+00:00", "Z")}","value":2}}\n',
        f'{{"timestamp":"{monthly.isoformat().replace("+00:00", "Z")}","value":3}}\n',
        f'{{"timestamp":"{purge.isoformat().replace("+00:00", "Z")}","value":4}}\n',
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


def test_dry_run_preserves_a_preexisting_temporary_file(tmp_path: Path) -> None:
    now = metrics_retention._now_utc()
    metrics_path = tmp_path / "metrics.ndjson"
    _write_lines(metrics_path, ['{"timestamp":"2025-01-02T00:00:00Z"}\n'])
    metrics_before = metrics_path.read_bytes()
    temporary_path = metrics_path.with_suffix(".ndjson.tmp")
    temporary_path.write_text("stale temporary data\n", encoding="utf-8")
    policy = metrics_retention.RetentionPolicy(7, 4, 6, True, tmp_path / "archives")

    stats = metrics_retention.apply_retention_to_file(metrics_path, policy, now=now, dry_run=True)

    assert stats.bytes_after == stats.bytes_before
    assert metrics_path.read_bytes() == metrics_before
    assert temporary_path.read_text(encoding="utf-8") == "stale temporary data\n"


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
    lines = [f'{{"timestamp":"{recent.isoformat().replace("+00:00", "Z")}","value":1}}\n']
    lines += [
        f'{{"timestamp":"{older.isoformat().replace("+00:00", "Z")}","value":{idx}}}\n'
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
        f'{{"timestamp":"{recent.isoformat().replace("+00:00", "Z")}","value":1}}\n'
        f'{{"timestamp":"{recent.isoformat().replace("+00:00", "Z")}","value":2}}\n',
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


def test_main_defaults_include_agents_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
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
                "archive": {"enabled": False, "storage_dir": str(tmp_path / "archives")},
            }
        ),
        encoding="utf-8",
    )
    metrics_path = tmp_path / ".agents" / "autopilot-metrics.ndjson"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text('{"timestamp":"2025-01-01T00:00:00Z","value":1}\n', encoding="utf-8")
    log_path = tmp_path / "metrics-retention.ndjson"

    exit_code = metrics_retention.main(
        [
            "--config",
            str(config_path),
            "--log-path",
            str(log_path),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    log_records = [json.loads(line) for line in _load_lines(log_path)]
    assert log_records[-1]["record_type"] == "retention_summary"
    assert log_records[-1]["dry_run"] is True
    assert log_records[-1]["files_processed"] == 1


def test_main_no_metrics_files_writes_noop_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "retention-policy.json"
    log_path = tmp_path / "metrics-retention.ndjson"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "retention": {
                    "daily": {"keep_days": 1},
                    "weekly": {"keep_weeks": 1},
                    "monthly": {"keep_months": 1},
                },
                "archive": {"enabled": False, "storage_dir": str(tmp_path / "archives")},
            }
        ),
        encoding="utf-8",
    )

    exit_code = metrics_retention.main(
        [
            "--config",
            str(config_path),
            "--log-path",
            str(log_path),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    # Falsifiable smoke for the no-op branch message (scripts/metrics_retention.py).
    # If the printed summary string changes, this assertion must fail.
    captured = capsys.readouterr()
    assert "no metrics files found; wrote no-op summary" in captured.out
    log_records = [json.loads(line) for line in _load_lines(log_path)]
    assert log_records == [
        {
            "bytes_after": 0,
            "bytes_archived": 0,
            "bytes_before": 0,
            "component": "metrics_retention",
            "dry_run": True,
            "files_processed": 0,
            "met_reduction_target": None,
            "min_reduction_percent": None,
            "parse_errors": 0,
            "record_type": "retention_summary",
            "records_archived_monthly": 0,
            "records_archived_weekly": 0,
            "records_kept": 0,
            "records_purged": 0,
            "records_skipped": 0,
            "records_total": 0,
            "reduction_percent": 0.0,
            "schema_version": 1,
            "timestamp": log_records[0]["timestamp"],
        }
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2024-06-15T12:00:00Z", datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)),
        (
            "2024-06-15T17:30:00+05:30",
            datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
        ),
        ("2024-06-15T12:00:00+00:00", datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)),
        ("2024-06-15T12:00:00", datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)),
        ("", None),
        ("   ", None),
        ("not-a-timestamp", None),
        ("2024-13-45T99:99:99Z", None),
    ],
)
def test_parse_iso_timestamp_boundary_cases(raw: str, expected: datetime | None) -> None:
    assert metrics_retention._parse_iso_timestamp(raw) == expected


@pytest.mark.parametrize(
    ("value", "months", "expected"),
    [
        (
            datetime(2025, 1, 31, 12, 0, 0, tzinfo=UTC),
            1,
            datetime(2024, 12, 31, 12, 0, 0, tzinfo=UTC),
        ),
        (
            datetime(2025, 3, 31, 12, 0, 0, tzinfo=UTC),
            1,
            datetime(2025, 2, 28, 12, 0, 0, tzinfo=UTC),
        ),
        (
            datetime(2024, 3, 31, 12, 0, 0, tzinfo=UTC),
            1,
            datetime(2024, 2, 29, 12, 0, 0, tzinfo=UTC),
        ),
        (
            datetime(2024, 2, 29, 12, 0, 0, tzinfo=UTC),
            1,
            datetime(2024, 1, 29, 12, 0, 0, tzinfo=UTC),
        ),
        (
            datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
            0,
            datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        ),
    ],
)
def test_subtract_months_boundary_cases(
    value: datetime,
    months: int,
    expected: datetime,
) -> None:
    assert metrics_retention._subtract_months(value, months) == expected


def test_apply_retention_to_file_cutoff_boundaries(tmp_path: Path, monkeypatch) -> None:
    fixed_now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(metrics_retention, "_now_utc", lambda: fixed_now)

    metrics_path = tmp_path / "metrics-history.ndjson"
    archive_root = tmp_path / "archives"
    policy = metrics_retention.RetentionPolicy(
        keep_days=7,
        keep_weeks=4,
        keep_months=1,
        archive_enabled=True,
        archive_dir=archive_root,
    )

    daily_cutoff = fixed_now - timedelta(days=policy.keep_days)
    weekly_cutoff = fixed_now - timedelta(weeks=policy.keep_weeks)
    monthly_cutoff = metrics_retention._subtract_months(fixed_now, policy.keep_months)

    after_daily = daily_cutoff + timedelta(hours=1)
    on_daily = daily_cutoff
    before_daily = daily_cutoff - timedelta(seconds=1)
    on_weekly = weekly_cutoff
    between_weekly_and_monthly = weekly_cutoff - timedelta(days=1)
    on_monthly = monthly_cutoff
    before_monthly = monthly_cutoff - timedelta(seconds=1)

    cases = {
        "after_daily": (after_daily, "kept"),
        "on_daily": (on_daily, "kept"),
        "before_daily": (before_daily, "weekly"),
        "on_weekly": (on_weekly, "weekly"),
        "between_weekly_and_monthly": (between_weekly_and_monthly, "monthly"),
        "on_monthly": (on_monthly, "monthly"),
        "before_monthly": (before_monthly, "purged"),
    }

    lines = [
        f'{{"timestamp":"{ts.isoformat().replace("+00:00", "Z")}","case":"{name}"}}\n'
        for name, (ts, _bucket) in cases.items()
    ]
    _write_lines(metrics_path, lines)

    stats = metrics_retention.apply_retention_to_file(
        metrics_path,
        policy,
        now=fixed_now,
        dry_run=False,
    )

    remaining = _load_lines(metrics_path)
    remaining_cases = {json.loads(line)["case"] for line in remaining}
    assert remaining_cases == {"after_daily", "on_daily"}

    weekly_cases: set[str] = set()
    monthly_cases: set[str] = set()
    for period in ("weekly", "monthly"):
        period_root = archive_root / "metrics-history" / period
        if not period_root.exists():
            continue
        for archive_file in period_root.glob("*.ndjson"):
            for line in _load_lines(archive_file):
                case_name = json.loads(line)["case"]
                if period == "weekly":
                    weekly_cases.add(case_name)
                else:
                    monthly_cases.add(case_name)

    assert weekly_cases == {"before_daily", "on_weekly"}
    assert monthly_cases == {"between_weekly_and_monthly", "on_monthly"}
    assert stats.records_kept == 2
    assert stats.records_archived_weekly == 2
    assert stats.records_archived_monthly == 2
    assert stats.records_purged == 1


def test_apply_retention_to_file_preserves_jsonl_payloads(tmp_path: Path) -> None:
    fixed_now = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
    metrics_path = tmp_path / "workflow-metrics.ndjson"
    archive_root = tmp_path / "archives"
    policy = metrics_retention.RetentionPolicy(
        keep_days=1,
        keep_weeks=2,
        keep_months=1,
        archive_enabled=True,
        archive_dir=archive_root,
    )

    kept_line = '{"timestamp":"2025-06-15T10:00:00Z","nested":{"count":1},"tags":["a","b"]}\n'
    weekly_line = '{"timestamp":"2025-06-10T10:00:00Z","nested":{"count":2},"tags":["c"]}\n'
    monthly_line = '{"timestamp":"2025-05-20T10:00:00Z","nested":{"count":3},"tags":[]}\n'
    original_lines = [kept_line, weekly_line, monthly_line]
    _write_lines(metrics_path, original_lines)
    original_bytes = metrics_path.read_bytes()

    stats = metrics_retention.apply_retention_to_file(
        metrics_path,
        policy,
        now=fixed_now,
        dry_run=False,
    )

    assert stats.records_kept == 1
    assert stats.records_archived_weekly == 1
    assert stats.records_archived_monthly == 1

    kept_bytes = metrics_path.read_bytes()
    assert kept_bytes == kept_line.encode("utf-8")
    assert kept_bytes != original_bytes

    weekly_bucket = metrics_retention._bucket_for_week(
        metrics_retention._parse_iso_timestamp("2025-06-10T10:00:00Z")
    )
    weekly_archive = archive_root / "workflow-metrics" / "weekly" / weekly_bucket
    monthly_bucket = metrics_retention._bucket_for_month(
        metrics_retention._parse_iso_timestamp("2025-05-20T10:00:00Z")
    )
    monthly_archive = archive_root / "workflow-metrics" / "monthly" / monthly_bucket

    assert weekly_archive.read_text(encoding="utf-8") == weekly_line
    assert monthly_archive.read_text(encoding="utf-8") == monthly_line


def test_helpers_cover_numeric_dates_policy_and_restore_dry_run(tmp_path: Path) -> None:
    assert metrics_retention._parse_timestamp_value(True) is None
    assert metrics_retention._parse_timestamp_value(0) == datetime(1970, 1, 1, tzinfo=UTC)
    assert metrics_retention._extract_timestamp({"created_at": "2025-01-01T00:00:00Z"}) is not None
    assert metrics_retention.FileRetentionStats(tmp_path / "none").reduction_percent() == 0.0
    config = tmp_path / "retention.json"
    config.write_text('{"retention": {}, "archive": {"enabled": false}}', encoding="utf-8")
    policy = metrics_retention.load_policy(config, archive_override=str(tmp_path / "override"))
    assert (
        policy.keep_days == 14
        and not policy.archive_enabled
        and policy.archive_dir == tmp_path / "override"
    )
    archive = tmp_path / "archive.ndjson"
    archive.write_text('{"value": 1}\n', encoding="utf-8")
    output = tmp_path / "out.ndjson"
    result = metrics_retention.restore_archive(archive, output, dedupe=False, dry_run=True)
    assert result["records_restored"] == 1
    assert not output.exists()
    output.write_text("existing\n", encoding="utf-8")
    metrics_retention.restore_archive(archive, output, dedupe=False, dry_run=True)
    assert output.read_text(encoding="utf-8") == "existing\n"
    with pytest.raises(FileNotFoundError):
        metrics_retention.restore_archive(
            tmp_path / "nope", tmp_path / "out", dedupe=False, dry_run=False
        )


def test_retention_helpers_cover_no_change_and_archive_disabled(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.ndjson"
    metrics.write_text('{"timestamp":"2025-01-01T00:00:00Z"}\n', encoding="utf-8")
    policy = metrics_retention.RetentionPolicy(1, 1, 1, False, tmp_path / "archive")
    stats = metrics_retention.apply_retention_to_file(
        metrics, policy, now=datetime(2025, 2, 1, tzinfo=UTC), dry_run=False
    )
    assert stats.records_kept == 1 and not (tmp_path / "metrics.ndjson.tmp").exists()
    assert (
        metrics_retention._iter_metrics_paths(
            [str(metrics), str(metrics)], [str(tmp_path / "nope")], metrics, include_defaults=False
        )
        == []
    )
    assert metrics_retention._iter_metrics_paths(
        [str(metrics), str(metrics)],
        [str(tmp_path)],
        tmp_path / "other.log",
        include_defaults=False,
    ) == [metrics]


def test_parse_timestamp_overflow_and_write_line_without_newline(tmp_path: Path) -> None:
    assert metrics_retention._parse_timestamp_value(10**100) is None
    sink = tmp_path / "line.txt"
    with sink.open("w", encoding="utf-8") as handle:
        metrics_retention._write_line(handle, "no-newline")
    assert sink.read_text(encoding="utf-8") == "no-newline\n"


def test_iter_paths_skips_empty_entries_and_load_policy_missing(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.ndjson"
    metrics.write_text("{}\n", encoding="utf-8")
    assert metrics_retention._iter_metrics_paths(
        ["", str(metrics)],
        [str(tmp_path)],
        tmp_path / "retention.log",
        include_defaults=False,
    ) == [metrics]
    with pytest.raises(FileNotFoundError, match="Retention config not found"):
        metrics_retention.load_policy(tmp_path / "missing.json")


def test_apply_retention_missing_file_blank_lines_and_dry_run_archive(tmp_path: Path) -> None:
    missing = tmp_path / "absent.ndjson"
    policy = metrics_retention.RetentionPolicy(7, 4, 6, True, tmp_path / "archive")
    now = datetime(2025, 6, 15, tzinfo=UTC)
    assert (
        metrics_retention.apply_retention_to_file(
            missing, policy, now=now, dry_run=False
        ).records_total
        == 0
    )

    metrics = tmp_path / "metrics.ndjson"
    weekly = (now - timedelta(days=10)).isoformat().replace("+00:00", "Z")
    monthly = (now - timedelta(days=40)).isoformat().replace("+00:00", "Z")
    metrics.write_text(
        f'\n{{"timestamp":"{weekly}","value":1}}\n\n{{"timestamp":"{monthly}","value":2}}\n',
        encoding="utf-8",
    )
    stats = metrics_retention.apply_retention_to_file(metrics, policy, now=now, dry_run=True)
    assert stats.records_archived_weekly == 1
    assert stats.records_archived_monthly == 1
    assert stats.bytes_archived > 0
    assert metrics.read_text(encoding="utf-8").count('"value"') == 2
    assert not (tmp_path / "metrics.ndjson.tmp").exists()


def test_main_restore_requires_archive_and_output(capsys) -> None:
    with pytest.raises(SystemExit):
        metrics_retention.main(["--restore"])
    err = capsys.readouterr().err
    assert "archive-path" in err and "output-path" in err


def test_restore_archive_from_directory_with_dedupe_write(tmp_path: Path) -> None:
    archive_root = tmp_path / "archives"
    weekly = archive_root / "metrics" / "weekly"
    weekly.mkdir(parents=True)
    (weekly / "2025-W01.ndjson").write_text(
        '{"value":1}\n\n{"value":2}\n{"value":1}\n',
        encoding="utf-8",
    )
    output = tmp_path / "out.ndjson"
    output.write_text('{"value":1}\n', encoding="utf-8")
    result = metrics_retention.restore_archive(archive_root, output, dedupe=True, dry_run=False)
    assert result["records_restored"] == 1
    assert result["records_skipped"] == 2
    assert '{"value":2}' in output.read_text(encoding="utf-8")


def test_main_restore_mode_writes_log(tmp_path: Path, capsys, monkeypatch) -> None:
    archive = tmp_path / "archive.ndjson"
    archive.write_text('{"value":9}\n', encoding="utf-8")
    output = tmp_path / "restored.ndjson"
    log_path = tmp_path / "retention.log"
    monkeypatch.setattr(
        metrics_retention,
        "_now_utc",
        lambda: datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
    )
    assert (
        metrics_retention.main(
            [
                "--restore",
                "--archive-path",
                str(archive),
                "--output-path",
                str(output),
                "--log-path",
                str(log_path),
            ]
        )
        == 0
    )
    assert output.read_text(encoding="utf-8") == '{"value":9}\n'
    assert "restored 1 records" in capsys.readouterr().out
    assert '"record_type": "restore"' in log_path.read_text(encoding="utf-8")
