from scripts import keepalive_metrics_dashboard as dashboard


def test_safe_int_handles_empty_invalid() -> None:
    assert dashboard._safe_int(None) is None
    assert dashboard._safe_int("") is None
    assert dashboard._safe_int("nope") is None
    assert dashboard._safe_int("5") == 5


def test_read_ndjson_handles_invalid_lines(tmp_path) -> None:
    path = tmp_path / "metrics.ndjson"
    path.write_text(
        "\n".join(
            [
                "",
                '{"pr_number": 10, "iteration": 2, "error_category": "none"}',
                "[1, 2, 3]",
                "{bad json}",
            ]
        ),
        encoding="utf-8",
    )

    entries, errors = dashboard._read_ndjson(path)

    assert entries == [{"pr_number": 10, "iteration": 2, "error_category": "none"}]
    assert errors == 2


def test_read_ndjson_missing_file(tmp_path) -> None:
    entries, errors = dashboard._read_ndjson(tmp_path / "missing.ndjson")

    assert entries == []
    assert errors == 1


def test_format_rate_handles_zero_denominator() -> None:
    assert dashboard._format_rate(1, 0) == "n/a"
    assert dashboard._format_rate(1, -1) == "n/a"
    assert dashboard._format_rate(2, 4) == "50.0% (2/4)"


def test_summarise_normalizes_categories_and_iterations() -> None:
    summary = dashboard._summarise(
        [
            {"pr_number": 1, "iteration": 1, "error_category": None},
            {"pr_number": 1, "iteration": 3, "error_category": "none"},
            {"pr_number": 2, "iteration": "2", "error_category": "Timeout"},
            {"pr_number": 3, "iteration": "bad", "error_category": ""},
        ]
    )

    assert summary["total"] == 4
    assert summary["successes"] == 1
    assert summary["error_breakdown"]["unknown"] == 2
    assert summary["error_breakdown"]["none"] == 1
    assert summary["error_breakdown"]["Timeout"] == 1
    assert summary["iteration_counts"]["1"] == 1
    assert summary["iteration_counts"]["2"] == 1
    assert summary["iteration_counts"]["3"] == 1
    assert summary["avg_iterations"] == 2.5


def test_build_parser_defaults() -> None:
    parser = dashboard._build_parser()
    args = parser.parse_args([])

    assert args.path == "keepalive-metrics.ndjson"
    assert args.output == "keepalive-metrics-dashboard.md"


def test_main_missing_path_returns_error(capsys) -> None:
    result = dashboard.main(["--path", "missing.ndjson"])

    captured = capsys.readouterr()
    assert result == 1
    assert "keepalive_metrics_dashboard: log not found" in captured.err


def test_main_writes_output(tmp_path, capsys) -> None:
    log_path = tmp_path / "metrics.ndjson"
    log_path.write_text('{"pr_number": 7, "iteration": 2, "error_category": "none"}', encoding="utf-8")
    output_path = tmp_path / "out" / "dashboard.md"

    result = dashboard.main(["--path", str(log_path), "--output", str(output_path)])

    captured = capsys.readouterr()
    assert result == 0
    assert output_path.exists()
    assert "# Keepalive Metrics Dashboard" in output_path.read_text(encoding="utf-8")
    assert "Wrote keepalive metrics dashboard to" in captured.out

def test_build_dashboard_handles_empty_records() -> None:
    output = dashboard.build_dashboard([], errors=0)

    assert "| Total records | 0 |" in output
    assert "| Success rate | n/a |" in output
    assert "| Avg iterations per PR | n/a |" in output
    assert "| Iteration distribution | n/a |" in output
    assert "| Error breakdown | n/a |" in output


def test_build_dashboard_single_record() -> None:
    records = [
        {
            "pr_number": 5,
            "iteration": 1,
            "error_category": "none",
        }
    ]

    output = dashboard.build_dashboard(records, errors=0)

    assert "| Total records | 1 |" in output
    assert "| Success rate | 100.0% (1/1) |" in output
    assert "| Avg iterations per PR | 1.0 |" in output
    assert "| Iteration distribution | 1 (1) |" in output
    assert "| Error breakdown | none (1) |" in output


def test_build_dashboard_multiple_records() -> None:
    records = [
        {
            "pr_number": 1,
            "iteration": 1,
            "error_category": "none",
        },
        {
            "pr_number": 1,
            "iteration": 2,
            "error_category": "timeout",
        },
        {
            "pr_number": 2,
            "iteration": 1,
            "error_category": "none",
        },
    ]

    output = dashboard.build_dashboard(records, errors=2)

    assert "| Total records | 3 |" in output
    assert "| Success rate | 66.7% (2/3) |" in output
    assert "| Avg iterations per PR | 1.5 |" in output
    assert "| Iteration distribution | 1 (2), 2 (1) |" in output
    assert "| Error breakdown | none (2), timeout (1) |" in output
    assert "| Parse errors | 2 |" in output
