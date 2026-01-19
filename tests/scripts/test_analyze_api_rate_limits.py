from __future__ import annotations

from datetime import UTC, datetime

from scripts import analyze_api_rate_limits


def test_parse_github_timestamp() -> None:
    parsed = analyze_api_rate_limits._parse_github_timestamp("2025-01-02T03:04:05Z")
    assert parsed is not None
    assert parsed.year == 2025
    assert parsed.month == 1
    assert parsed.day == 2
    assert parsed.tzinfo == UTC
    assert analyze_api_rate_limits._parse_github_timestamp("not-a-time") is None


def test_summarize_workflow_activity_filters_window(monkeypatch) -> None:
    runs = [
        {"created_at": "2025-01-01T10:00:00Z"},
        {"created_at": "2025-01-01T08:59:59Z"},
        {"created_at": "not-a-time"},
        {},
    ]

    def fake_get_workflow_runs(_repo: str, token: str | None = None) -> dict[str, object]:
        return {"workflow_runs": runs, "total_count": 4}

    monkeypatch.setattr(analyze_api_rate_limits, "get_workflow_runs", fake_get_workflow_runs)
    now = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
    summaries = analyze_api_rate_limits.summarize_workflow_activity(
        ["owner/repo"],
        token="token",
        hours=2,
        now=now,
    )
    assert summaries == [
        {
            "repo": "owner/repo",
            "window_hours": 2,
            "recent_runs": 1,
            "total_runs": 4,
        }
    ]


def test_summarize_workflow_activity_falls_back_to_other_timestamps(monkeypatch) -> None:
    runs = [
        {"run_started_at": "2025-01-01T10:30:00Z"},
        {"created_at": "not-a-time", "updated_at": "2025-01-01T10:45:00Z"},
        {"updated_at": "2025-01-01T09:59:59Z"},
    ]

    def fake_get_workflow_runs(_repo: str, token: str | None = None) -> dict[str, object]:
        return {"workflow_runs": runs, "total_count": 3}

    monkeypatch.setattr(analyze_api_rate_limits, "get_workflow_runs", fake_get_workflow_runs)
    now = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
    summaries = analyze_api_rate_limits.summarize_workflow_activity(
        ["owner/repo"],
        token="token",
        hours=1,
        now=now,
    )
    assert summaries[0]["recent_runs"] == 2
