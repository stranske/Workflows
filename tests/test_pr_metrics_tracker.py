"""Tests for pr_metrics_tracker module."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.pr_metrics_tracker import (
    PRMetrics,
    calculate_autofix_rate,
    calculate_average_merge_time,
    generate_metrics_summary,
    group_by_label,
    load_pr_history,
    parse_pr_data,
)


class TestPRMetrics:
    """Tests for PRMetrics dataclass."""

    def test_time_to_merge_merged_pr(self) -> None:
        """Test time calculation for merged PR."""
        created = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        merged = datetime(2025, 1, 1, 12, 30, 0, tzinfo=timezone.utc)

        pr = PRMetrics(
            pr_number=1,
            created_at=created,
            merged_at=merged,
            review_count=2,
            commit_count=3,
            autofix_applied=True,
            labels=["enhancement"],
        )

        # 2.5 hours difference
        assert pr.time_to_merge_hours() == 2.5

    def test_time_to_merge_unmerged_pr(self) -> None:
        """Test time calculation for unmerged PR."""
        pr = PRMetrics(
            pr_number=1,
            created_at=datetime.now(timezone.utc),
            merged_at=None,
            review_count=0,
            commit_count=1,
            autofix_applied=False,
            labels=[],
        )

        assert pr.time_to_merge_hours() is None


class TestParsePRData:
    """Tests for parse_pr_data function."""

    def test_parse_merged_pr(self) -> None:
        """Test parsing a merged PR."""
        data = {
            "number": 123,
            "created_at": "2025-01-01T10:00:00Z",
            "merged_at": "2025-01-01T12:00:00Z",
            "review_comments": 5,
            "commits": 3,
            "labels": [
                {"name": "autofix:applied"},
                {"name": "enhancement"},
            ],
        }

        pr = parse_pr_data(data)
        assert pr.pr_number == 123
        assert pr.merged_at is not None
        assert pr.autofix_applied is True
        assert "enhancement" in pr.labels

    def test_parse_unmerged_pr(self) -> None:
        """Test parsing an unmerged PR."""
        data = {
            "number": 456,
            "created_at": "2025-01-01T10:00:00Z",
            "merged_at": None,
            "labels": [],
        }

        pr = parse_pr_data(data)
        assert pr.pr_number == 456
        assert pr.merged_at is None
        assert pr.autofix_applied is False


class TestLoadPRHistory:
    """Tests for load_pr_history function."""

    def test_load_empty_file(self, tmp_path: Path) -> None:
        """Test loading empty history file."""
        history_file = tmp_path / "history.ndjson"
        history_file.write_text("")

        metrics = load_pr_history(str(history_file))
        assert metrics == []

    def test_load_missing_file(self) -> None:
        """Test loading missing history file."""
        metrics = load_pr_history("/nonexistent/history.ndjson")
        assert metrics == []

    def test_load_valid_history(self, tmp_path: Path) -> None:
        """Test loading valid history file."""
        history_file = tmp_path / "history.ndjson"
        records = [
            {"number": 1, "created_at": "2025-01-01T10:00:00Z", "labels": []},
            {"number": 2, "created_at": "2025-01-02T10:00:00Z", "labels": []},
        ]
        history_file.write_text("\n".join(json.dumps(r) for r in records))

        metrics = load_pr_history(str(history_file))
        assert len(metrics) == 2


class TestCalculateAverageMergeTime:
    """Tests for calculate_average_merge_time function."""

    def test_average_with_merged_prs(self) -> None:
        """Test average calculation with merged PRs."""
        base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        metrics = [
            PRMetrics(1, base, base + timedelta(hours=2), 0, 1, False, []),
            PRMetrics(2, base, base + timedelta(hours=4), 0, 1, False, []),
        ]

        avg = calculate_average_merge_time(metrics)
        assert avg == 3.0  # (2 + 4) / 2

    def test_average_with_no_merged_prs(self) -> None:
        """Test average calculation with no merged PRs."""
        base = datetime.now(timezone.utc)
        metrics = [
            PRMetrics(1, base, None, 0, 1, False, []),
            PRMetrics(2, base, None, 0, 1, False, []),
        ]

        avg = calculate_average_merge_time(metrics)
        assert avg == 0.0

    def test_average_empty_list(self) -> None:
        """Test average calculation with empty list."""
        avg = calculate_average_merge_time([])
        assert avg == 0.0


class TestCalculateAutofixRate:
    """Tests for calculate_autofix_rate function."""

    def test_rate_with_autofix_prs(self) -> None:
        """Test autofix rate calculation."""
        base = datetime.now(timezone.utc)
        metrics = [
            PRMetrics(1, base, None, 0, 1, True, []),
            PRMetrics(2, base, None, 0, 1, False, []),
            PRMetrics(3, base, None, 0, 1, True, []),
            PRMetrics(4, base, None, 0, 1, False, []),
        ]

        rate = calculate_autofix_rate(metrics)
        assert rate == 50.0  # 2/4 = 50%

    def test_rate_empty_list(self) -> None:
        """Test autofix rate with empty list."""
        rate = calculate_autofix_rate([])
        assert rate == 0.0


class TestGroupByLabel:
    """Tests for group_by_label function."""

    def test_group_prs_by_label(self) -> None:
        """Test grouping PRs by their labels."""
        base = datetime.now(timezone.utc)
        metrics = [
            PRMetrics(1, base, None, 0, 1, False, ["bug", "urgent"]),
            PRMetrics(2, base, None, 0, 1, False, ["enhancement"]),
            PRMetrics(3, base, None, 0, 1, False, ["bug"]),
        ]

        grouped = group_by_label(metrics)
        assert len(grouped["bug"]) == 2
        assert len(grouped["enhancement"]) == 1
        assert len(grouped["urgent"]) == 1

    def test_group_empty_list(self) -> None:
        """Test grouping empty list."""
        grouped = group_by_label([])
        assert grouped == {}


class TestGenerateMetricsSummary:
    """Tests for generate_metrics_summary function."""

    def test_summary_generation(self) -> None:
        """Test summary generation with mixed PRs."""
        base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        metrics = [
            PRMetrics(1, base, base + timedelta(hours=2), 2, 3, True, []),
            PRMetrics(2, base, None, 1, 2, False, []),
        ]

        summary = generate_metrics_summary(metrics)
        assert summary["total_prs"] == 2
        assert summary["merged_prs"] == 1
        assert summary["autofix_rate_percent"] == 50.0
        assert summary["avg_review_count"] == 1.5  # (2+1)/2

    def test_summary_empty_list(self) -> None:
        """Test summary with empty list."""
        summary = generate_metrics_summary([])
        assert summary["total_prs"] == 0
        assert summary["merged_prs"] == 0
        assert summary["autofix_rate_percent"] == 0.0
