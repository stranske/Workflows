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

    assert "## Per-Repo Summary" in output
    assert "### octo/alpha" in output
    assert "### octo/beta" in output
    assert "| Metric | Mean | P50 | P90 | P99 | Trend |" in output
    assert "Entries: 2" in output
    assert "Entries: 1" in output


def test_build_dashboard_handles_missing_fields() -> None:
    output = generator.build_dashboard([], errors=0)

    assert "No repo metrics found." in output
