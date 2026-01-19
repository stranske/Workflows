from __future__ import annotations

import json
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


def test_parse_github_timestamp_assumes_utc_for_naive() -> None:
    parsed = analyze_api_rate_limits._parse_github_timestamp("2025-01-02T03:04:05")
    assert parsed is not None
    assert parsed.tzinfo == UTC


def test_summarize_workflow_activity_handles_naive_now(monkeypatch) -> None:
    runs = [
        {"created_at": "2025-01-01T10:30:00Z"},
        {"created_at": "2025-01-01T08:59:59Z"},
    ]

    def fake_get_workflow_runs(_repo: str, token: str | None = None) -> dict[str, object]:
        return {"workflow_runs": runs, "total_count": 2}

    monkeypatch.setattr(analyze_api_rate_limits, "get_workflow_runs", fake_get_workflow_runs)
    now = datetime(2025, 1, 1, 11, 0, 0)
    summaries = analyze_api_rate_limits.summarize_workflow_activity(
        ["owner/repo"],
        token="token",
        hours=1,
        now=now,
    )
    assert summaries[0]["recent_runs"] == 1


def test_summarize_workflow_activity_handles_naive_run_timestamps(monkeypatch) -> None:
    runs = [
        {"created_at": "2025-01-01T10:30:00"},
        {"created_at": "2025-01-01T08:59:59"},
    ]

    def fake_get_workflow_runs(_repo: str, token: str | None = None) -> dict[str, object]:
        return {"workflow_runs": runs, "total_count": 2}

    monkeypatch.setattr(analyze_api_rate_limits, "get_workflow_runs", fake_get_workflow_runs)
    now = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
    summaries = analyze_api_rate_limits.summarize_workflow_activity(
        ["owner/repo"],
        token="token",
        hours=1,
        now=now,
    )
    assert summaries[0]["recent_runs"] == 1


def test_summarize_workflow_activity_normalizes_repos(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get_workflow_runs(repo: str, token: str | None = None) -> dict[str, object]:
        calls.append(repo)
        return {"workflow_runs": [], "total_count": 0}

    monkeypatch.setattr(analyze_api_rate_limits, "get_workflow_runs", fake_get_workflow_runs)
    now = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
    summaries = analyze_api_rate_limits.summarize_workflow_activity(
        [" owner/repo ", "owner2/repo2, owner3/repo3", ""],
        token="token",
        hours=1,
        now=now,
    )

    assert calls == ["owner/repo", "owner2/repo2", "owner3/repo3"]
    assert [summary["repo"] for summary in summaries] == calls


def test_summarize_workflow_activity_dedupes_repos(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get_workflow_runs(repo: str, token: str | None = None) -> dict[str, object]:
        calls.append(repo)
        return {"workflow_runs": [], "total_count": 0}

    monkeypatch.setattr(analyze_api_rate_limits, "get_workflow_runs", fake_get_workflow_runs)
    now = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
    summaries = analyze_api_rate_limits.summarize_workflow_activity(
        ["owner/repo", "owner/repo", "owner/repo, owner2/repo2"],
        token="token",
        hours=1,
        now=now,
    )

    assert calls == ["owner/repo", "owner2/repo2"]
    assert [summary["repo"] for summary in summaries] == calls


def test_summarize_workflow_activity_normalizes_repo_urls(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get_workflow_runs(repo: str, token: str | None = None) -> dict[str, object]:
        calls.append(repo)
        return {"workflow_runs": [], "total_count": 0}

    monkeypatch.setattr(analyze_api_rate_limits, "get_workflow_runs", fake_get_workflow_runs)
    now = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
    summaries = analyze_api_rate_limits.summarize_workflow_activity(
        [
            "https://github.com/owner/repo",
            "git@github.com:owner/repo.git",
            "owner/repo/",
        ],
        token="token",
        hours=1,
        now=now,
    )

    assert calls == ["owner/repo"]
    assert [summary["repo"] for summary in summaries] == calls


def test_main_json_includes_workflow_activity(monkeypatch, capsys) -> None:
    token_limits = analyze_api_rate_limits.TokenRateLimits(
        source="GITHUB_TOKEN",
        core=analyze_api_rate_limits.RateLimitInfo(
            limit=5000, remaining=4500, used=500, reset_timestamp=0
        ),
        graphql=analyze_api_rate_limits.RateLimitInfo(
            limit=5000, remaining=4500, used=500, reset_timestamp=0
        ),
        search=analyze_api_rate_limits.RateLimitInfo(
            limit=5000, remaining=4500, used=500, reset_timestamp=0
        ),
        code_search=analyze_api_rate_limits.RateLimitInfo(
            limit=20, remaining=15, used=5, reset_timestamp=0
        ),
        actions_runner=analyze_api_rate_limits.RateLimitInfo(
            limit=10, remaining=9, used=1, reset_timestamp=0
        ),
    )

    def fake_analyze_rate_limits(
        _tokens: dict[str, str | None],
    ) -> list[analyze_api_rate_limits.TokenRateLimits]:
        return [token_limits]

    def fake_summarize_workflow_activity(
        repos: list[str],
        *,
        token: str | None = None,
        hours: int = 1,
        now: datetime | None = None,
    ) -> list[dict[str, object]]:
        assert repos == ["owner/repo"]
        assert token == "token"
        assert hours == 2
        return [
            {
                "repo": "owner/repo",
                "window_hours": 2,
                "recent_runs": 0,
                "total_runs": 0,
            }
        ]

    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(analyze_api_rate_limits, "analyze_rate_limits", fake_analyze_rate_limits)
    monkeypatch.setattr(
        analyze_api_rate_limits, "summarize_workflow_activity", fake_summarize_workflow_activity
    )
    monkeypatch.setattr(
        analyze_api_rate_limits.sys,
        "argv",
        ["script", "--json", "--check-repos", "owner/repo", "--workflow-hours", "2"],
    )

    assert analyze_api_rate_limits.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["workflow_activity"] == [
        {
            "repo": "owner/repo",
            "window_hours": 2,
            "recent_runs": 0,
            "total_runs": 0,
        }
    ]
    token_payload = payload["tokens"]["GITHUB_TOKEN"]
    assert token_payload["code_search"] == analyze_api_rate_limits._rate_limit_payload(
        token_limits.code_search
    )
    assert token_payload[
        "actions_runner_registration"
    ] == analyze_api_rate_limits._rate_limit_payload(token_limits.actions_runner)


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


def test_summarize_workflow_activity_falls_back_total_count(monkeypatch) -> None:
    runs = [{"created_at": "2025-01-01T10:00:00Z"}]

    def fake_get_workflow_runs(_repo: str, token: str | None = None) -> dict[str, object]:
        return {"workflow_runs": runs, "total_count": None}

    monkeypatch.setattr(analyze_api_rate_limits, "get_workflow_runs", fake_get_workflow_runs)
    now = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
    summaries = analyze_api_rate_limits.summarize_workflow_activity(
        ["owner/repo"],
        token="token",
        hours=2,
        now=now,
    )
    assert summaries[0]["total_runs"] == 1


def test_summarize_workflow_activity_handles_non_list_runs(monkeypatch) -> None:
    def fake_get_workflow_runs(_repo: str, token: str | None = None) -> dict[str, object]:
        return {"workflow_runs": None, "total_count": None}

    monkeypatch.setattr(analyze_api_rate_limits, "get_workflow_runs", fake_get_workflow_runs)
    now = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
    summaries = analyze_api_rate_limits.summarize_workflow_activity(
        ["owner/repo"],
        token="token",
        hours=2,
        now=now,
    )
    assert summaries[0]["recent_runs"] == 0
    assert summaries[0]["total_runs"] == 0


def test_summarize_workflow_activity_ignores_non_dict_runs(monkeypatch) -> None:
    runs = [{"created_at": "2025-01-01T10:00:00Z"}, "oops", 123]

    def fake_get_workflow_runs(_repo: str, token: str | None = None) -> dict[str, object]:
        return {"workflow_runs": runs, "total_count": None}

    monkeypatch.setattr(analyze_api_rate_limits, "get_workflow_runs", fake_get_workflow_runs)
    now = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
    summaries = analyze_api_rate_limits.summarize_workflow_activity(
        ["owner/repo"],
        token="token",
        hours=2,
        now=now,
    )
    assert summaries[0]["recent_runs"] == 1
    assert summaries[0]["total_runs"] == 1


def test_print_warnings_includes_optional_resources(capsys) -> None:
    limits = [
        analyze_api_rate_limits.TokenRateLimits(
            source="GITHUB_TOKEN",
            core=analyze_api_rate_limits.RateLimitInfo(
                limit=5000, remaining=4500, used=500, reset_timestamp=0
            ),
            graphql=analyze_api_rate_limits.RateLimitInfo(
                limit=5000, remaining=4500, used=500, reset_timestamp=0
            ),
            search=analyze_api_rate_limits.RateLimitInfo(
                limit=30, remaining=30, used=0, reset_timestamp=0
            ),
            code_search=analyze_api_rate_limits.RateLimitInfo(
                limit=10, remaining=1, used=9, reset_timestamp=0
            ),
            actions_runner=analyze_api_rate_limits.RateLimitInfo(
                limit=10, remaining=1, used=9, reset_timestamp=0
            ),
        )
    ]

    warnings = analyze_api_rate_limits.print_warnings(limits)
    _ = capsys.readouterr()

    assert any("Code Search" in warning for warning in warnings)
    assert any("Actions Runner Registration" in warning for warning in warnings)


def test_print_utilization_table_includes_optional_resources(capsys) -> None:
    limits = [
        analyze_api_rate_limits.TokenRateLimits(
            source="GITHUB_TOKEN",
            core=analyze_api_rate_limits.RateLimitInfo(
                limit=5000, remaining=4500, used=500, reset_timestamp=0
            ),
            graphql=analyze_api_rate_limits.RateLimitInfo(
                limit=5000, remaining=4500, used=500, reset_timestamp=0
            ),
            search=analyze_api_rate_limits.RateLimitInfo(
                limit=30, remaining=30, used=0, reset_timestamp=0
            ),
            code_search=analyze_api_rate_limits.RateLimitInfo(
                limit=10, remaining=1, used=9, reset_timestamp=0
            ),
            actions_runner=analyze_api_rate_limits.RateLimitInfo(
                limit=10, remaining=1, used=9, reset_timestamp=0
            ),
        )
    ]

    analyze_api_rate_limits.print_utilization_table(limits)
    output = capsys.readouterr().out

    assert "OPTIONAL RESOURCE UTILIZATION" in output
    assert "Code Search" in output
    assert "Actions Runner Registration" in output


def test_print_utilization_table_skips_optional_section_without_resources(capsys) -> None:
    limits = [
        analyze_api_rate_limits.TokenRateLimits(
            source="GITHUB_TOKEN",
            core=analyze_api_rate_limits.RateLimitInfo(
                limit=5000, remaining=4500, used=500, reset_timestamp=0
            ),
            graphql=analyze_api_rate_limits.RateLimitInfo(
                limit=5000, remaining=4500, used=500, reset_timestamp=0
            ),
            search=analyze_api_rate_limits.RateLimitInfo(
                limit=30, remaining=30, used=0, reset_timestamp=0
            ),
        )
    ]

    analyze_api_rate_limits.print_utilization_table(limits)
    output = capsys.readouterr().out

    assert "OPTIONAL RESOURCE UTILIZATION" not in output
