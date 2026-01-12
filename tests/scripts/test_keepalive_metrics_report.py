from pathlib import Path

from scripts import keepalive_metrics_report as report


def _write_log(path: Path, payloads: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(payloads), encoding="utf-8")


def test_main_collects_metrics_from_repos(tmp_path: Path, capsys) -> None:
    metrics_dir = tmp_path / "metrics"
    repo_a = metrics_dir / "stranske-workflows"
    repo_b = metrics_dir / "stranske-other"
    _write_log(
        repo_a / "keepalive-metrics.ndjson",
        [
            (
                '{"pr_number":1,"iteration":1,"timestamp":"2025-01-01T00:00:00Z",'
                '"action":"run","error_category":"none","duration_ms":10,'
                '"tasks_total":2,"tasks_complete":1}'
            )
        ],
    )
    _write_log(
        repo_b / "keepalive-metrics.ndjson",
        [
            (
                '{"pr_number":2,"iteration":2,"timestamp":"2025-01-02T00:00:00Z",'
                '"action":"run","error_category":"none","duration_ms":20,'
                '"tasks_total":4,"tasks_complete":4}'
            )
        ],
    )

    output_ndjson = tmp_path / "out" / "combined.ndjson"
    output_dashboard = tmp_path / "out" / "dashboard.md"

    result = report.main(
        [
            "--metrics-dir",
            str(metrics_dir),
            "--repos",
            "stranske/workflows,stranske/other",
            "--output-ndjson",
            str(output_ndjson),
            "--output-dashboard",
            str(output_dashboard),
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert output_ndjson.exists()
    assert output_dashboard.exists()
    contents = output_ndjson.read_text(encoding="utf-8").splitlines()
    assert len(contents) == 2
    assert "Wrote combined metrics" in captured.out
    assert "# Keepalive Metrics Dashboard" in output_dashboard.read_text(encoding="utf-8")


def test_main_reports_missing_repos(tmp_path: Path, capsys) -> None:
    metrics_dir = tmp_path / "metrics"
    _write_log(
        metrics_dir / "stranske-workflows" / "keepalive-metrics.ndjson",
        [
            (
                '{"pr_number":1,"iteration":1,"timestamp":"2025-01-01T00:00:00Z",'
                '"action":"run","error_category":"none","duration_ms":10,'
                '"tasks_total":2,"tasks_complete":1}'
            )
        ],
    )

    output_ndjson = tmp_path / "out" / "combined.ndjson"
    output_dashboard = tmp_path / "out" / "dashboard.md"

    result = report.main(
        [
            "--metrics-dir",
            str(metrics_dir),
            "--repos",
            "stranske/workflows,stranske/missing",
            "--output-ndjson",
            str(output_ndjson),
            "--output-dashboard",
            str(output_dashboard),
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "missing repos" in captured.err
    assert output_ndjson.exists()
    assert output_dashboard.exists()


def test_main_counts_invalid_records(tmp_path: Path) -> None:
    metrics_dir = tmp_path / "metrics"
    _write_log(
        metrics_dir / "stranske-workflows" / "keepalive-metrics.ndjson",
        [
            "not-json",
            (
                '{"pr_number":1,"iteration":1,"timestamp":"2025-01-01T00:00:00Z",'
                '"action":"run","error_category":"none","duration_ms":10,'
                '"tasks_total":2,"tasks_complete":1}'
            ),
            (
                '{"pr_number":1,"iteration":1,"timestamp":"2025-01-01T00:00:00Z",'
                '"action":"run","error_category":"none","duration_ms":"fast",'
                '"tasks_total":2,"tasks_complete":1}'
            ),
        ],
    )

    output_ndjson = tmp_path / "out" / "combined.ndjson"
    output_dashboard = tmp_path / "out" / "dashboard.md"

    result = report.main(
        [
            "--metrics-dir",
            str(metrics_dir),
            "--output-ndjson",
            str(output_ndjson),
            "--output-dashboard",
            str(output_dashboard),
        ]
    )

    assert result == 1
    contents = output_ndjson.read_text(encoding="utf-8").splitlines()
    assert len(contents) == 1
