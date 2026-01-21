import json
from pathlib import Path

from scripts import aggregate_repo_metrics, metrics_dashboard_generator


def _write_repo_metrics(metrics_dir: Path, fixture_path: Path) -> list[str]:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    repos = payload["repos"]
    metrics_dir.mkdir(parents=True, exist_ok=True)
    for repo, entries in repos.items():
        path = metrics_dir / f"{repo.replace('/', '__')}.ndjson"
        lines = [json.dumps(entry, sort_keys=True) for entry in entries]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sorted(repos.keys())


def test_metrics_dashboard_pipeline(tmp_path: Path) -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "sample_metrics.json"
    metrics_dir = tmp_path / "repo-metrics"
    repos = _write_repo_metrics(metrics_dir, fixture_path)

    combined_path = tmp_path / "combined-repo-metrics.ndjson"
    summary_path = tmp_path / "repo-metrics-summary.json"

    exit_code = aggregate_repo_metrics.main(
        [
            "--repos",
            ",".join(repos),
            "--metrics-dir",
            str(metrics_dir),
            "--output",
            str(combined_path),
            "--summary-output",
            str(summary_path),
            "--numeric-field",
            "duration_ms",
            "--numeric-field",
            "success_rate",
            "--numeric-field",
            "failed_jobs",
        ]
    )

    assert exit_code == 0
    assert combined_path.exists()
    assert summary_path.exists()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["total_entries"] == 4
    assert set(summary["numeric_fields"]) == {"duration_ms", "success_rate", "failed_jobs"}

    combined_entries = [
        json.loads(line)
        for line in combined_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    raw_entries = [entry for entry in combined_entries if entry.get("repo") in repos]
    assert len(raw_entries) == 4
    assert any(entry.get("entry_type") == "aggregate" for entry in combined_entries)

    dashboard_path = tmp_path / "dashboard.md"
    dashboard_exit = metrics_dashboard_generator.main(
        [
            "--path",
            str(combined_path),
            "--output",
            str(dashboard_path),
            "--fields",
            "duration_ms",
            "success_rate",
            "failed_jobs",
        ]
    )

    assert dashboard_exit == 0
    content = dashboard_path.read_text(encoding="utf-8")
    assert "# Weekly Metrics Dashboard" in content
    assert "## Org Summary" in content
    assert "## Per-Repo Summary" in content
    assert "## Repo Details" in content
    assert "### octo/alpha" in content
    assert "### octo/beta" in content


def test_metrics_dashboard_pipeline_with_config(tmp_path: Path) -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "sample_metrics.json"
    metrics_dir = tmp_path / "repo-metrics"
    repos = _write_repo_metrics(metrics_dir, fixture_path)

    combined_path = tmp_path / "combined-repo-metrics.ndjson"
    summary_path = tmp_path / "repo-metrics-summary.json"

    exit_code = aggregate_repo_metrics.main(
        [
            "--repos",
            ",".join(repos),
            "--metrics-dir",
            str(metrics_dir),
            "--output",
            str(combined_path),
            "--summary-output",
            str(summary_path),
            "--numeric-field",
            "duration_ms",
            "--numeric-field",
            "success_rate",
            "--numeric-field",
            "failed_jobs",
        ]
    )

    assert exit_code == 0
    assert combined_path.exists()
    assert summary_path.exists()

    config_path = tmp_path / "dashboard-config.json"
    dashboard_path = tmp_path / "dashboard.md"
    config_path.write_text(
        json.dumps(
            {
                "metrics_path": str(combined_path),
                "output_path": str(dashboard_path),
                "numeric_fields": ["duration_ms", "success_rate", "failed_jobs"],
                "thresholds": {
                    "duration_ms": {"ok": 120000, "warn": 150000, "higher_is_better": False},
                    "success_rate": {"ok": 98, "warn": 95, "higher_is_better": True},
                    "failed_jobs": {"ok": 0, "warn": 2, "higher_is_better": False},
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    dashboard_exit = metrics_dashboard_generator.main(["--config", str(config_path)])

    assert dashboard_exit == 0
    content = dashboard_path.read_text(encoding="utf-8")
    assert "# Weekly Metrics Dashboard" in content
    assert "Parse errors: 0" in content
    assert "| Metric | Mean | P50 | P90 | P99 | Trend | Status |" in content
    assert "| duration_ms |" in content
    assert "| success_rate |" in content
    assert "| failed_jobs |" in content
