from pathlib import Path

from scripts import metrics_dashboard_generator as generator


def test_build_dashboard_includes_repo_sections() -> None:
    entries = [
        {
            "repo": "octo/alpha",
            "duration_ms": 10,
            "timestamp": "2024-01-01T00:00:00Z",
        },
        {
            "repo": "octo/alpha",
            "duration_ms": 20,
            "timestamp": "2024-01-02T00:00:00Z",
        },
        {
            "repo": "octo/beta",
            "duration_ms": 5,
            "timestamp": "2024-01-01T00:00:00Z",
        },
    ]

    output = generator.build_dashboard(entries, errors=1)

    assert "## Org Summary" in output
    assert "| Metric | Mean | P50 | P90 | P99 | Trend | Status |" in output
    assert "## Per-Repo Summary" in output
    assert "| Repo | Entries | Metrics tracked | Last update |" in output
    assert "| octo/alpha | 2 | 1 | 2024-01-02T00:00:00Z |" in output
    assert "| octo/beta | 1 | 1 | 2024-01-01T00:00:00Z |" in output
    assert "## Repo Details" in output
    assert "### octo/alpha" in output
    assert "### octo/beta" in output
    assert "| Metric | Mean | P50 | P90 | P99 | Trend | Status |" in output
    assert "Entries: 2" in output
    assert "Entries: 1" in output


def test_build_dashboard_handles_missing_fields() -> None:
    output = generator.build_dashboard([], errors=0)

    assert "No repo metrics found." in output


def test_parse_field_list_splits_commas() -> None:
    fields = generator._parse_field_list(["duration_ms,coverage", "failures"])

    assert fields == ["duration_ms", "coverage", "failures"]


def test_load_config_validates_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        (
            '{'
            '"metrics_path": "metrics.ndjson", '
            '"output_path": "out.md", '
            '"numeric_fields": ["a", "b"], '
            '"thresholds": {"duration_ms": {"ok": 10, "warn": 20, "higher_is_better": false}}'
            '}'
        ),
        encoding="utf-8",
    )

    config = generator._validate_config(generator._load_config(config_path))

    assert config["metrics_path"] == "metrics.ndjson"
    assert config["output_path"] == "out.md"
    assert config["numeric_fields"] == ["a", "b"]
    assert config["thresholds"]["duration_ms"]["ok"] == 10.0
    assert config["thresholds"]["duration_ms"]["warn"] == 20.0
    assert config["thresholds"]["duration_ms"]["higher_is_better"] is False


def test_build_dashboard_includes_status_thresholds() -> None:
    entries = [
        {"repo": "octo/alpha", "duration_ms": 10, "timestamp": "2024-01-01T00:00:00Z"},
        {"repo": "octo/alpha", "duration_ms": 20, "timestamp": "2024-01-02T00:00:00Z"},
    ]
    thresholds = {"duration_ms": {"ok": 15, "warn": 25, "higher_is_better": False}}

    output = generator.build_dashboard(entries, errors=0, thresholds=thresholds)

    assert "| duration_ms |" in output
    assert "| WARN |" in output


def test_main_writes_output(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.ndjson"
    metrics_path.write_text(
        "\n".join(
            [
                '{"repo": "octo/alpha", "duration_ms": 10, "timestamp": "2024-01-01T00:00:00Z"}',
                '{"repo": "octo/alpha", "duration_ms": 20, "timestamp": "2024-01-02T00:00:00Z"}',
            ]
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "dashboard.md"

    exit_code = generator.main(
        ["--path", str(metrics_path), "--output", str(output_path), "--fields", "duration_ms"]
    )

    assert exit_code == 0
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "# Weekly Metrics Dashboard" in content
