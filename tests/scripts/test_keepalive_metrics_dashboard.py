from scripts import keepalive_metrics_dashboard as dashboard


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
