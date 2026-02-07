from tools import ci_failure_triage


def test_extract_pytest_failures_parses_unique() -> None:
    log_text = "\n".join(
        [
            "FAILED tests/workflows/test_keepalive_workflow.py::test_keepalive_requires_dispatch_token - AssertionError",
            "FAILED tests/workflows/test_keepalive_workflow.py::test_keepalive_prefers_dedicated_dispatch_token[param] - ValueError",
            "FAILED tests/workflows/test_keepalive_workflow.py::test_keepalive_requires_dispatch_token - AssertionError",
        ]
    )

    failures = ci_failure_triage.extract_pytest_failures(log_text)

    assert failures == [
        "tests/workflows/test_keepalive_workflow.py::test_keepalive_requires_dispatch_token",
        "tests/workflows/test_keepalive_workflow.py::test_keepalive_prefers_dedicated_dispatch_token[param]",
    ]


def test_triage_report_includes_failed_tests() -> None:
    log_text = "\n".join(
        [
            "=================================== FAILURES ===================================",
            "FAILED tests/workflows/test_keepalive_workflow.py::test_keepalive_requires_dispatch_token - AssertionError",
        ]
    )

    report = ci_failure_triage.triage_ci_failure(log_text)

    assert report.failed_tests == [
        "tests/workflows/test_keepalive_workflow.py::test_keepalive_requires_dispatch_token"
    ]
    assert "Pytest failures: 1" in report.summary
