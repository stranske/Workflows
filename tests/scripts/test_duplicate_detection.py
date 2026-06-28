from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts import duplicate_detection
from scripts.langchain import issue_dedup


class TestBackoffDelay:
    """Tests for _backoff_delay helper function."""

    def test_zero_interval_returns_zero(self) -> None:
        assert duplicate_detection._backoff_delay(0.0, 0) == 0.0
        assert duplicate_detection._backoff_delay(0.0, 5) == 0.0

    def test_negative_interval_returns_zero(self) -> None:
        assert duplicate_detection._backoff_delay(-1.0, 0) == 0.0
        assert duplicate_detection._backoff_delay(-0.5, 3) == 0.0

    def test_exponential_backoff(self) -> None:
        base = 1.0
        assert duplicate_detection._backoff_delay(base, 0) == 1.0  # 1 * 2^0
        assert duplicate_detection._backoff_delay(base, 1) == 2.0  # 1 * 2^1
        assert duplicate_detection._backoff_delay(base, 2) == 4.0  # 1 * 2^2
        assert duplicate_detection._backoff_delay(base, 3) == 8.0  # 1 * 2^3

    def test_exponential_backoff_with_custom_base(self) -> None:
        base = 0.5
        assert duplicate_detection._backoff_delay(base, 0) == 0.5  # 0.5 * 2^0
        assert duplicate_detection._backoff_delay(base, 1) == 1.0  # 0.5 * 2^1
        assert duplicate_detection._backoff_delay(base, 2) == 2.0  # 0.5 * 2^2

    def test_clamping_to_max_backoff(self) -> None:
        base = 100.0
        max_backoff = duplicate_detection.MAX_BACKOFF_SECONDS
        # 100 * 2^0 = 100, which is > 60, so clamped
        assert duplicate_detection._backoff_delay(base, 0) == max_backoff
        # 100 * 2^1 = 200, which is > 60, so clamped
        assert duplicate_detection._backoff_delay(base, 1) == max_backoff
        # 100 * 2^2 = 400, which is > 60, so clamped
        assert duplicate_detection._backoff_delay(base, 2) == max_backoff


class TestApiRetryKwargs:
    """Tests for _api_retry_kwargs helper function."""

    def test_none_values_returns_empty_dict(self) -> None:
        result = duplicate_detection._api_retry_kwargs(None, None)
        assert result == {}

    def test_retry_attempts_only(self) -> None:
        result = duplicate_detection._api_retry_kwargs(retry_attempts=5, retry_backoff=None)
        assert result == {"retry_attempts": 5}

    def test_retry_backoff_only(self) -> None:
        result = duplicate_detection._api_retry_kwargs(retry_attempts=None, retry_backoff=2.0)
        assert result == {"retry_backoff": 2.0}

    def test_both_values(self) -> None:
        result = duplicate_detection._api_retry_kwargs(retry_attempts=3, retry_backoff=1.5)
        assert result == {"retry_attempts": 3, "retry_backoff": 1.5}


class TestWaitForDedupComment:
    """Tests for _wait_for_dedup_comment helper function."""

    @patch("scripts.duplicate_detection.time.sleep")
    @patch("scripts.api_client.fetch_issue_comments")
    def test_returns_comment_on_first_attempt(
        self, mock_fetch: MagicMock, mock_sleep: MagicMock
    ) -> None:
        expected_comment = {"body": "Comment with " + issue_dedup.SIMILAR_ISSUES_MARKER}
        mock_fetch.return_value = [expected_comment]

        result = duplicate_detection._wait_for_dedup_comment(
            repo="owner/repo",
            issue_number=123,
            token="fake-token",
            attempts=3,
            interval=1.0,
        )

        assert result == expected_comment
        assert mock_fetch.call_count == 1
        mock_sleep.assert_not_called()

    @patch("scripts.duplicate_detection.time.sleep")
    @patch("scripts.api_client.fetch_issue_comments")
    def test_returns_none_when_no_comment_found(
        self, mock_fetch: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_fetch.return_value = [{"body": "Regular comment"}]

        result = duplicate_detection._wait_for_dedup_comment(
            repo="owner/repo",
            issue_number=123,
            token="fake-token",
            attempts=3,
            interval=1.0,
        )

        assert result is None
        assert mock_fetch.call_count == 3
        assert mock_sleep.call_count == 2  # Sleeps between attempts

    @patch("scripts.duplicate_detection.time.sleep")
    @patch("scripts.api_client.fetch_issue_comments")
    def test_returns_comment_on_second_attempt(
        self, mock_fetch: MagicMock, mock_sleep: MagicMock
    ) -> None:
        expected_comment = {"body": "Has " + issue_dedup.SIMILAR_ISSUES_MARKER}
        mock_fetch.side_effect = [
            [{"body": "No marker"}],
            [expected_comment],
        ]

        result = duplicate_detection._wait_for_dedup_comment(
            repo="owner/repo",
            issue_number=123,
            token="fake-token",
            attempts=3,
            interval=1.0,
        )

        assert result == expected_comment
        assert mock_fetch.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("scripts.duplicate_detection.time.sleep")
    @patch("scripts.api_client.fetch_issue_comments")
    def test_respects_minimum_one_attempt(
        self, mock_fetch: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_fetch.return_value = [{"body": "Regular comment"}]

        result = duplicate_detection._wait_for_dedup_comment(
            repo="owner/repo",
            issue_number=123,
            token="fake-token",
            attempts=0,  # Should be treated as 1
            interval=1.0,
        )

        assert result is None
        assert mock_fetch.call_count == 1
        mock_sleep.assert_not_called()

    @patch("scripts.duplicate_detection.time.sleep")
    @patch("scripts.api_client.fetch_issue_comments")
    def test_sleeps_with_backoff_delay(self, mock_fetch: MagicMock, mock_sleep: MagicMock) -> None:
        mock_fetch.return_value = [{"body": "No marker"}]

        duplicate_detection._wait_for_dedup_comment(
            repo="owner/repo",
            issue_number=123,
            token="fake-token",
            attempts=4,
            interval=1.0,
        )

        # Should sleep 3 times (between 4 attempts)
        assert mock_sleep.call_count == 3
        # First sleep: 1.0 * 2^0 = 1.0
        mock_sleep.assert_any_call(1.0)
        # Second sleep: 1.0 * 2^1 = 2.0
        mock_sleep.assert_any_call(2.0)
        # Third sleep: 1.0 * 2^2 = 4.0
        mock_sleep.assert_any_call(4.0)

    @patch("scripts.duplicate_detection.time.sleep")
    @patch("scripts.api_client.fetch_issue_comments")
    def test_zero_interval_no_sleep(self, mock_fetch: MagicMock, mock_sleep: MagicMock) -> None:
        mock_fetch.return_value = [{"body": "No marker"}]

        duplicate_detection._wait_for_dedup_comment(
            repo="owner/repo",
            issue_number=123,
            token="fake-token",
            attempts=3,
            interval=0.0,
        )

        assert mock_fetch.call_count == 3
        mock_sleep.assert_not_called()

    @patch("scripts.duplicate_detection.time.sleep")
    @patch("scripts.api_client.fetch_issue_comments")
    def test_passes_retry_kwargs_to_api_client(
        self, mock_fetch: MagicMock, mock_sleep: MagicMock
    ) -> None:
        duplicate_detection._wait_for_dedup_comment(
            repo="owner/repo",
            issue_number=123,
            token="fake-token",
            attempts=1,
            interval=1.0,
            retry_attempts=5,
            retry_backoff=2.0,
        )

        mock_fetch.assert_called_once()
        call_kwargs = mock_fetch.call_args.kwargs
        assert call_kwargs.get("retry_attempts") == 5
        assert call_kwargs.get("retry_backoff") == 2.0


class TestCheckIssueForDuplicate:
    """Tests for check_issue_for_duplicate function."""

    @patch("scripts.duplicate_detection._wait_for_dedup_comment")
    def test_returns_comment_when_found(self, mock_wait: MagicMock) -> None:
        mock_wait.return_value = {"body": "Found comment"}

        result = duplicate_detection.check_issue_for_duplicate(
            repo="owner/repo",
            issue_number=123,
            token="fake-token",
            attempts=3,
            interval=1.0,
        )

        assert result == {"body": "Found comment"}
        mock_wait.assert_called_once()

    @patch("scripts.duplicate_detection._wait_for_dedup_comment")
    def test_returns_none_when_not_found(self, mock_wait: MagicMock) -> None:
        mock_wait.return_value = None

        result = duplicate_detection.check_issue_for_duplicate(
            repo="owner/repo",
            issue_number=123,
            token="fake-token",
            attempts=3,
            interval=1.0,
        )

        assert result is None


class TestCheckIssueForNoDuplicate:
    """Tests for check_issue_for_no_duplicate function."""

    @patch("scripts.duplicate_detection._wait_for_dedup_comment")
    def test_returns_false_when_comment_found(self, mock_wait: MagicMock) -> None:
        mock_wait.return_value = {"body": "Found comment"}

        result = duplicate_detection.check_issue_for_no_duplicate(
            repo="owner/repo",
            issue_number=123,
            token="fake-token",
            attempts=3,
            interval=1.0,
        )

        assert result is False

    @patch("scripts.duplicate_detection._wait_for_dedup_comment")
    def test_returns_true_when_no_comment_found(self, mock_wait: MagicMock) -> None:
        mock_wait.return_value = None

        result = duplicate_detection.check_issue_for_no_duplicate(
            repo="owner/repo",
            issue_number=123,
            token="fake-token",
            attempts=3,
            interval=1.0,
        )

        assert result is True
