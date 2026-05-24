from pathlib import Path

DOC = Path("docs/contracts/langsmith-observability-contract.md")


def test_langsmith_observability_contract_doc_covers_shared_vs_domain_boundary() -> None:
    content = DOC.read_text(encoding="utf-8")

    assert "Workflows owns" in content
    assert "Consumer repos own" in content
    assert "Shared vs Domain Metadata" in content
    assert "domain" in content


def test_langsmith_observability_contract_doc_defines_dashboard_statuses() -> None:
    content = DOC.read_text(encoding="utf-8")

    for status in ("`missing`", "`invalid`", "`stale`", "`valid`"):
        assert status in content


def test_langsmith_observability_contract_doc_lists_tracked_repo_issues() -> None:
    content = DOC.read_text(encoding="utf-8")

    expected_issues = [
        "stranske/trip-planner#1208",
        "stranske/Pension-Data#445",
        "stranske/Manager-Database#1048",
        "stranske/Counter_Risk#610",
        "stranske/Inv-Man-Intake#438",
        "stranske/Trend_Model_Project#5311",
        "stranske/Portable-Alpha-Extension-Model#1802",
    ]

    for issue in expected_issues:
        assert issue in content


def test_langsmith_observability_contract_doc_has_repo_issue_checklist() -> None:
    content = DOC.read_text(encoding="utf-8")

    assert "Repo Issue Implementation Checklist" in content
    assert "instrumentation code in the consumer repo" in content
    assert "link back to the parent Workflows LangSmith fleet issue" in content
