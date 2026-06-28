from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from scripts import duplicate_detection
from scripts.langchain import issue_dedup


class TestIssuePayloadHelpers:
    """Tests for issue payload and source issue helper functions."""

    def test_build_issue_payload_omits_optional_fields_when_empty(self) -> None:
        assert duplicate_detection.build_issue_payload("New issue", None, None) == {
            "title": "New issue"
        }
        assert duplicate_detection.build_issue_payload("New issue", None, []) == {
            "title": "New issue"
        }

    def test_build_issue_payload_includes_body_and_labels(self) -> None:
        assert duplicate_detection.build_issue_payload(
            "New issue", "Issue body", ["bug", "needs-triage"]
        ) == {
            "title": "New issue",
            "body": "Issue body",
            "labels": ["bug", "needs-triage"],
        }

    def test_format_body_with_note_appends_or_replaces_body(self) -> None:
        assert duplicate_detection.format_body_with_note("Existing body", None) == "Existing body"
        assert duplicate_detection.format_body_with_note("Existing body", "") == "Existing body"
        assert (
            duplicate_detection.format_body_with_note("Existing body", "Dedup note")
            == "Existing body\n\nDedup note"
        )
        assert duplicate_detection.format_body_with_note(None, "Dedup note") == "Dedup note"

    def test_parse_source_issue_accepts_numeric_string_and_html_url(self) -> None:
        source = duplicate_detection.parse_source_issue(
            {
                "number": "42",
                "title": "  Original issue  ",
                "body": "Original body",
                "html_url": "https://github.test/issues/42",
                "url": "https://api.github.test/issues/42",
            }
        )

        assert source == duplicate_detection.SourceIssue(
            number=42,
            title="Original issue",
            body="Original body",
            url="https://github.test/issues/42",
        )

    def test_parse_source_issue_uses_api_url_fallback(self) -> None:
        source = duplicate_detection.parse_source_issue(
            {
                "number": 43,
                "title": "Fallback URL",
                "body": None,
                "url": "https://api.github.test/issues/43",
            }
        )

        assert source.url == "https://api.github.test/issues/43"

    @pytest.mark.parametrize(
        "payload",
        [
            {"title": "Missing number"},
            {"number": "not-a-number", "title": "Bad number"},
            {"number": 44},
            {"number": 45, "title": "   "},
        ],
    )
    def test_parse_source_issue_rejects_missing_required_fields(
        self, payload: dict[str, object]
    ) -> None:
        with pytest.raises(ValueError):
            duplicate_detection.parse_source_issue(payload)

    def test_build_duplicate_payload_applies_suffix_note_and_labels(self) -> None:
        source = duplicate_detection.SourceIssue(
            number=50,
            title="Original issue",
            body="Original body",
            url="https://github.test/issues/50",
        )

        assert duplicate_detection.build_duplicate_payload(
            source,
            title_suffix=" (duplicate probe)",
            note="Created by duplicate detection smoke test.",
            labels=["duplicate-check"],
        ) == {
            "title": "Original issue (duplicate probe)",
            "body": "Original body\n\nCreated by duplicate detection smoke test.",
            "labels": ["duplicate-check"],
        }


class TestIssueQueryHelpers:
    """Tests for in-memory issue filtering and selection helpers."""

    def test_filter_issues_by_query_skips_pull_requests_and_malformed_issues(self) -> None:
        issues = [
            {
                "number": 1,
                "title": "Matching title",
                "body": "No body match",
                "html_url": "https://github.test/issues/1",
            },
            {
                "number": 2,
                "title": "Pull request match",
                "body": "matching body",
                "pull_request": {"url": "https://api.github.test/pulls/2"},
            },
            {"number": "bad", "title": "Matching but malformed"},
            {
                "number": 3,
                "title": "Unrelated",
                "body": "body has MATCHING keyword",
                "url": "https://api.github.test/issues/3",
            },
            {"number": 4, "title": "Unrelated", "body": "No keyword"},
        ]

        matches = duplicate_detection.filter_issues_by_query(issues, "matching")

        assert [match.number for match in matches] == [1, 3]
        assert [match.title for match in matches] == ["Matching title", "Unrelated"]

    def test_filter_issues_by_query_none_returns_valid_non_pull_request_issues(self) -> None:
        issues = [
            {"number": 10, "title": "First"},
            {"number": 11, "title": "Second", "pull_request": {}},
            {"number": 12, "title": ""},
            {"number": 13, "title": "Third"},
        ]

        matches = duplicate_detection.filter_issues_by_query(issues, None)

        assert [match.number for match in matches] == [10, 13]

    def test_select_issue_by_query_returns_first_match_or_none(self) -> None:
        issues = [
            {"number": 20, "title": "Alpha match"},
            {"number": 21, "title": "Beta match"},
        ]

        assert duplicate_detection.select_issue_by_query(issues, "match") == (
            duplicate_detection.SourceIssue(number=20, title="Alpha match", body=None, url=None)
        )
        assert duplicate_detection.select_issue_by_query(issues, "missing") is None


class TestSimilarIssueReferenceHelpers:
    """Tests for parsing and formatting duplicate-reference helpers."""

    def test_extract_similar_issue_refs_handles_links_bare_refs_titles_and_ignored_lines(
        self,
    ) -> None:
        comment_body = "\n".join(
            [
                issue_dedup.SIMILAR_ISSUES_MARKER,
                "This prose line should be ignored.",
                "- **#101** - [Login error on mobile](https://github.test/issues/101) (92% similarity)",
                "- #202 - Bare issue title (88% similarity)",
                "- [#303](https://github.test/issues/303) - Linked reference title",
                "- No issue number or link here",
                "  - Nested-looking item is ignored because it is not a top-level dash",
            ]
        )

        refs = duplicate_detection.extract_similar_issue_refs(comment_body)

        assert refs == [
            duplicate_detection.SimilarIssueRef(
                number=101,
                url="https://github.test/issues/101",
                title="Login error on mobile",
            ),
            duplicate_detection.SimilarIssueRef(number=202, url=None, title="Bare issue title"),
            duplicate_detection.SimilarIssueRef(
                number=303,
                url="https://github.test/issues/303",
                title="Linked reference title",
            ),
        ]

    def test_extract_similar_issue_refs_accepts_url_without_issue_number(self) -> None:
        refs = duplicate_detection.extract_similar_issue_refs(
            "- [External tracker](https://tracker.test/TICKET-9) - External duplicate"
        )

        assert refs == [
            duplicate_detection.SimilarIssueRef(
                number=None,
                url="https://tracker.test/TICKET-9",
                title="External duplicate",
            )
        ]

    def test_source_issue_formatters_include_unknown_url_fallback(self) -> None:
        source = duplicate_detection.SourceIssue(
            number=77,
            title="Potential duplicate",
            body=None,
            url=None,
        )

        assert (
            duplicate_detection.format_source_issue_line(source)
            == "Source issue: #77 Potential duplicate (unknown)"
        )
        assert (
            duplicate_detection.format_source_confirmation(source)
            == "Source issue confirmed: #77 Potential duplicate (unknown)"
        )

    def test_format_duplicate_confirmation_prefers_number_then_url_then_generic(self) -> None:
        assert (
            duplicate_detection.format_duplicate_confirmation(
                [
                    duplicate_detection.SimilarIssueRef(
                        number=88, url="https://github.test/issues/88", title="Match"
                    )
                ]
            )
            == "Duplicate detected and linked to #88."
        )
        assert (
            duplicate_detection.format_duplicate_confirmation(
                [
                    duplicate_detection.SimilarIssueRef(
                        number=None, url="https://tracker.test/TICKET-8", title="Match"
                    )
                ]
            )
            == "Duplicate detected and linked to https://tracker.test/TICKET-8."
        )
        assert (
            duplicate_detection.format_duplicate_confirmation([])
            == "Duplicate detected and linked to similar issue(s)."
        )

    def test_matches_expected_duplicate_checks_number_url_and_empty_expectation(self) -> None:
        refs = [
            duplicate_detection.SimilarIssueRef(
                number=90, url="https://github.test/issues/90/", title="First"
            ),
            duplicate_detection.SimilarIssueRef(
                number=None, url="https://tracker.test/TICKET-90", title="Second"
            ),
        ]

        assert duplicate_detection.matches_expected_duplicate(
            refs, expected_number=None, expected_url=None
        )
        assert duplicate_detection.matches_expected_duplicate(
            refs, expected_number=90, expected_url=None
        )
        assert duplicate_detection.matches_expected_duplicate(
            refs, expected_number=None, expected_url="https://github.test/issues/90"
        )
        assert not duplicate_detection.matches_expected_duplicate(
            refs, expected_number=91, expected_url="https://github.test/issues/91"
        )


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


class TestFindSourceIssue:
    """Tests for find_source_issue paginated source issue collection."""

    @patch("scripts.api_client.fetch_issues")
    def test_stops_after_matching_page(self, mock_fetch: MagicMock) -> None:
        matching_issue = [{"number": 42, "title": "Target issue", "body": "Found it"}]
        mock_fetch.side_effect = [
            [{"number": 1, "title": "No match"}],
            matching_issue,
        ]

        result = duplicate_detection.find_source_issue(
            repo="owner/repo",
            token="fake-token",
            query="Target",
            labels=None,
            pages=5,
        )

        assert result == duplicate_detection.SourceIssue(
            number=42, title="Target issue", body="Found it", url=None
        )
        assert mock_fetch.call_count == 2

    @patch("scripts.api_client.fetch_issues")
    def test_stops_on_empty_page(self, mock_fetch: MagicMock) -> None:
        mock_fetch.side_effect = [
            [{"number": 1, "title": "No match"}],
            [],
        ]

        result = duplicate_detection.find_source_issue(
            repo="owner/repo",
            token="fake-token",
            query="Target",
            labels=None,
            pages=5,
        )

        assert result is None
        assert mock_fetch.call_count == 2

    @patch("scripts.api_client.fetch_issues")
    def test_returns_none_when_no_match_in_all_pages(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = [{"number": 1, "title": "No match"}]

        result = duplicate_detection.find_source_issue(
            repo="owner/repo",
            token="fake-token",
            query="Target",
            labels=None,
            pages=3,
        )

        assert result is None
        assert mock_fetch.call_count == 3

    @patch("scripts.api_client.fetch_issues")
    def test_respects_minimum_one_page(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = [{"number": 1, "title": "No match"}]

        result = duplicate_detection.find_source_issue(
            repo="owner/repo",
            token="fake-token",
            query="Target",
            labels=None,
            pages=0,
        )

        assert result is None
        assert mock_fetch.call_count == 1

    @patch("scripts.api_client.fetch_issues")
    def test_passes_retry_kwargs_to_api_client(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = []

        duplicate_detection.find_source_issue(
            repo="owner/repo",
            token="fake-token",
            query="Target",
            labels=None,
            pages=1,
            retry_attempts=5,
            retry_backoff=2.0,
        )

        mock_fetch.assert_called_once()
        call_kwargs = mock_fetch.call_args.kwargs
        assert call_kwargs.get("retry_attempts") == 5
        assert call_kwargs.get("retry_backoff") == 2.0

    @patch("scripts.api_client.fetch_issues")
    def test_filters_out_pull_requests_and_malformed_during_search(
        self, mock_fetch: MagicMock
    ) -> None:
        mock_fetch.side_effect = [
            [
                {"number": 1, "title": "PR match", "pull_request": {}},
                {"number": "bad", "title": "Malformed"},
                {"number": 2, "title": "No match"},
            ],
            [{"number": 3, "title": "Target match"}],
        ]

        result = duplicate_detection.find_source_issue(
            repo="owner/repo",
            token="fake-token",
            query="Target",
            labels=None,
            pages=2,
        )

        assert result == duplicate_detection.SourceIssue(
            number=3, title="Target match", body=None, url=None
        )
        assert mock_fetch.call_count == 2


class TestCollectMatchingIssues:
    """Tests for collect_matching_issues paginated collection."""

    @patch("scripts.api_client.fetch_issues")
    def test_collects_across_pages_until_limit(self, mock_fetch: MagicMock) -> None:
        page1 = [
            {"number": 1, "title": "Match alpha", "body": "alpha"},
            {"number": 2, "title": "Match beta", "body": "beta"},
        ]
        page2 = [
            {"number": 3, "title": "Match gamma", "body": "gamma"},
            {"number": 4, "title": "No match", "body": "nope"},
        ]
        mock_fetch.side_effect = [page1, page2]

        result = duplicate_detection.collect_matching_issues(
            repo="owner/repo",
            token="fake-token",
            query="Match",
            labels=None,
            pages=5,
            limit=3,
        )

        assert len(result) == 3
        assert [r.number for r in result] == [1, 2, 3]
        assert mock_fetch.call_count == 2

    @patch("scripts.api_client.fetch_issues")
    def test_honors_limit_exactly(self, mock_fetch: MagicMock) -> None:
        page1 = [
            {"number": 1, "title": "Match alpha"},
            {"number": 2, "title": "Match beta"},
            {"number": 3, "title": "Match gamma"},
        ]
        mock_fetch.return_value = page1

        result = duplicate_detection.collect_matching_issues(
            repo="owner/repo",
            token="fake-token",
            query="Match",
            labels=None,
            pages=1,
            limit=2,
        )

        assert len(result) == 2
        assert [r.number for r in result] == [1, 2]

    @patch("scripts.api_client.fetch_issues")
    def test_stops_on_empty_page(self, mock_fetch: MagicMock) -> None:
        mock_fetch.side_effect = [
            [{"number": 1, "title": "Match alpha"}],
            [],
        ]

        result = duplicate_detection.collect_matching_issues(
            repo="owner/repo",
            token="fake-token",
            query="Match",
            labels=None,
            pages=5,
        )

        assert len(result) == 1
        assert result[0].number == 1
        assert mock_fetch.call_count == 2

    @patch("scripts.api_client.fetch_issues")
    def test_collects_all_matches_without_limit(self, mock_fetch: MagicMock) -> None:
        page1 = [{"number": 1, "title": "Match alpha"}]
        page2 = [{"number": 2, "title": "Match beta"}]
        page3 = [{"number": 3, "title": "Something else"}]
        mock_fetch.side_effect = [page1, page2, page3]

        result = duplicate_detection.collect_matching_issues(
            repo="owner/repo",
            token="fake-token",
            query="Match",
            labels=None,
            pages=3,
            limit=None,
        )

        assert len(result) == 2
        assert [r.number for r in result] == [1, 2]
        assert mock_fetch.call_count == 3

    @patch("scripts.api_client.fetch_issues")
    def test_respects_minimum_one_page(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = []

        result = duplicate_detection.collect_matching_issues(
            repo="owner/repo",
            token="fake-token",
            query="Match",
            labels=None,
            pages=0,
        )

        assert result == []
        assert mock_fetch.call_count == 1

    @patch("scripts.api_client.fetch_issues")
    def test_passes_retry_kwargs_to_api_client(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = []

        duplicate_detection.collect_matching_issues(
            repo="owner/repo",
            token="fake-token",
            query="Match",
            labels=None,
            pages=1,
            limit=10,
            retry_attempts=5,
            retry_backoff=2.0,
        )

        mock_fetch.assert_called_once()
        call_kwargs = mock_fetch.call_args.kwargs
        assert call_kwargs.get("retry_attempts") == 5
        assert call_kwargs.get("retry_backoff") == 2.0

    @patch("scripts.api_client.fetch_issues")
    def test_filters_out_pull_requests_and_malformed_during_collection(
        self, mock_fetch: MagicMock
    ) -> None:
        mock_fetch.return_value = [
            {"number": 1, "title": "Valid match", "body": "good"},
            {"number": 2, "title": "PR match", "pull_request": {}},
            {"number": "bad", "title": "Malformed match"},
            {"number": 3, "title": "Another match", "body": "also good"},
            {"number": 4, "title": "PR also", "pull_request": {"url": "..."}},
            {"number": "also_bad", "title": "Another malformed"},
        ]

        result = duplicate_detection.collect_matching_issues(
            repo="owner/repo",
            token="fake-token",
            query="match",
            labels=None,
            pages=1,
        )

        assert len(result) == 2
        assert [r.number for r in result] == [1, 3]
