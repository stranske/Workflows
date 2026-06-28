"""Tests for tools.disable_legacy_workflows module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tools.disable_legacy_workflows import (
    WorkflowAPIError,
    _extract_next_link,
    _normalize_allowlist,
    _normalized_slug,
    disable_legacy_workflows,
)


class TestNormalizedSlug:
    """Tests for _normalized_slug()."""

    def test_returns_name_unchanged_without_disabled_suffix(self) -> None:
        path = Path("workflow.yml")
        assert _normalized_slug(path) == "workflow.yml"

    def test_removes_disabled_suffix_from_yml_disabled(self) -> None:
        path = Path("workflow.yml.disabled")
        assert _normalized_slug(path) == "workflow.yml"

    def test_returns_name_unchanged_for_regular_file(self) -> None:
        path = Path("other.txt")
        assert _normalized_slug(path) == "other.txt"

    def test_handles_yml_disabled_suffix(self) -> None:
        path = Path("workflow.yml.disabled")
        assert _normalized_slug(path) == "workflow.yml"


class TestExtractNextLink:
    """Tests for _extract_next_link()."""

    def test_returns_none_for_none_header(self) -> None:
        assert _extract_next_link(None) is None

    def test_returns_none_for_empty_header(self) -> None:
        assert _extract_next_link("") is None

    def test_returns_none_for_header_without_next(self) -> None:
        header = '<https://api.github.com/repos/foo/bar>; rel="prev"'
        assert _extract_next_link(header) is None

    def test_extracts_next_link_url(self) -> None:
        header = '<https://api.github.com/repos/foo/bar?page=2>; rel="next"'
        result = _extract_next_link(header)
        assert result == "https://api.github.com/repos/foo/bar?page=2"

    def test_extracts_next_link_from_multiple_links(self) -> None:
        header = (
            '<https://api.github.com/repos/foo/bar?page=1>; rel="prev", '
            '<https://api.github.com/repos/foo/bar?page=3>; rel="next"'
        )
        result = _extract_next_link(header)
        assert result == "https://api.github.com/repos/foo/bar?page=3"

    def test_handles_next_link_without_angle_brackets(self) -> None:
        header = 'https://api.github.com/repos/foo/bar?page=2; rel="next"'
        result = _extract_next_link(header)
        assert result == "https://api.github.com/repos/foo/bar?page=2"

    def test_handles_whitespace_in_url(self) -> None:
        header = '<https://api.github.com/repos/foo/bar?page=2>; rel="next"'
        result = _extract_next_link(header)
        assert result == "https://api.github.com/repos/foo/bar?page=2"


class TestNormalizeAllowlist:
    """Tests for _normalize_allowlist()."""

    def test_returns_empty_set_for_empty_input(self) -> None:
        assert _normalize_allowlist([]) == set()

    def test_normalizes_single_value(self) -> None:
        result = _normalize_allowlist(["workflow.yml"])
        assert result == {"workflow.yml"}

    def test_splits_comma_separated_values(self) -> None:
        result = _normalize_allowlist(["workflow1.yml,workflow2.yml"])
        assert result == {"workflow1.yml", "workflow2.yml"}

    def test_strips_whitespace(self) -> None:
        result = _normalize_allowlist(["  workflow.yml  "])
        assert result == {"workflow.yml"}

    def test_handles_multiple_input_strings(self) -> None:
        result = _normalize_allowlist(["a.yml,b.yml", "c.yml"])
        assert result == {"a.yml", "b.yml", "c.yml"}

    def test_ignores_empty_tokens(self) -> None:
        result = _normalize_allowlist(["a.yml,,b.yml"])
        assert result == {"a.yml", "b.yml"}

    def test_ignores_whitespace_only_tokens(self) -> None:
        result = _normalize_allowlist(["a.yml,  ,b.yml"])
        assert result == {"a.yml", "b.yml"}


class TestWorkflowAPIError:
    """Tests for WorkflowAPIError class."""

    def test_str_returns_json_with_all_fields(self) -> None:
        import json

        error = WorkflowAPIError(
            status_code=404,
            reason="Not Found",
            url="https://api.github.com/repos/foo/bar",
            body='{"message": "not found"}',
        )
        result = str(error)
        parsed = json.loads(result)
        assert parsed == {
            "status_code": 404,
            "reason": "Not Found",
            "url": "https://api.github.com/repos/foo/bar",
            "body": '{"message": "not found"}',
        }

    def test_str_is_valid_json(self) -> None:
        import json

        error = WorkflowAPIError(
            status_code=500,
            reason="Internal Server Error",
            url="https://api.github.com/test",
            body="error details",
        )
        result = str(error)
        # Should not raise
        parsed = json.loads(result)
        assert isinstance(parsed, dict)


class TestDisableLegacyWorkflows:
    """Tests for disable_legacy_workflows() main function."""

    def test_dry_run_disables_non_canonical_workflows(self) -> None:
        """Test that dry-run mode collects disabled/kept without making HTTP calls."""
        mock_workflows = [
            {"id": 1, "name": "Canonical CI", "path": ".github/workflows/ci.yml"},
            {"id": 2, "name": "Legacy Workflow", "path": ".github/workflows/legacy.yml"},
        ]

        with (
            patch(
                "tools.disable_legacy_workflows._list_all_workflows",
                return_value=mock_workflows,
            ),
            patch(
                "tools.disable_legacy_workflows._http_request",
                return_value=(b"", {}),
            ),
            patch(
                "tools.disable_legacy_workflows.CANONICAL_WORKFLOW_FILES",
                {"ci.yml"},
            ),
        ):
            result = disable_legacy_workflows(
                repository="test/repo",
                token="fake-token",
                dry_run=True,
            )

        assert "Canonical CI" in result["kept"]
        assert "Legacy Workflow" in result["disabled"]
        assert result["skipped"] == []

    def test_keeps_allowlisted_workflows(self) -> None:
        """Test that allowlisted workflows are kept."""
        mock_workflows = [
            {"id": 1, "name": "Allowed Workflow", "path": ".github/workflows/custom.yml"},
            {"id": 2, "name": "Normal Workflow", "path": ".github/workflows/normal.yml"},
        ]

        with (
            patch(
                "tools.disable_legacy_workflows._list_all_workflows",
                return_value=mock_workflows,
            ),
            patch(
                "tools.disable_legacy_workflows._http_request",
                return_value=(b"", {}),
            ),
            patch(
                "tools.disable_legacy_workflows.CANONICAL_WORKFLOW_FILES",
                set(),  # No canonical workflows
            ),
        ):
            result = disable_legacy_workflows(
                repository="test/repo",
                token="fake-token",
                dry_run=True,
                extra_allow=["custom.yml"],
            )

        assert "Allowed Workflow" in result["kept"]
        assert "Normal Workflow" in result["disabled"]

    def test_extra_allow_with_comma_separated_values(self) -> None:
        """Test that extra_allow handles comma-separated values."""
        mock_workflows = [
            {"id": 1, "name": "Workflow A", "path": ".github/workflows/a.yml"},
            {"id": 2, "name": "Workflow B", "path": ".github/workflows/b.yml"},
            {"id": 3, "name": "Workflow C", "path": ".github/workflows/c.yml"},
        ]

        with (
            patch(
                "tools.disable_legacy_workflows._list_all_workflows",
                return_value=mock_workflows,
            ),
            patch(
                "tools.disable_legacy_workflows._http_request",
                return_value=(b"", {}),
            ),
            patch(
                "tools.disable_legacy_workflows.CANONICAL_WORKFLOW_FILES",
                set(),
            ),
        ):
            result = disable_legacy_workflows(
                repository="test/repo",
                token="fake-token",
                dry_run=True,
                extra_allow=["a.yml,b.yml"],
            )

        assert "Workflow A" in result["kept"]
        assert "Workflow B" in result["kept"]
        assert "Workflow C" in result["disabled"]

    def test_skips_workflows_with_api_error(self) -> None:
        """Test that workflows causing API errors are skipped."""
        mock_workflows = [
            {"id": 1, "name": "Good Workflow", "path": ".github/workflows/good.yml"},
            {"id": 2, "name": "Bad Workflow", "path": ".github/workflows/bad.yml"},
        ]

        def mock_http_request(*args, **kwargs):
            # Raise error for bad workflow (id=2)
            if args and len(args) >= 2 and args[1] and "2" in str(args[1]):
                raise WorkflowAPIError(
                    status_code=404,
                    reason="Not Found",
                    url="https://api.github.com/test",
                    body="not found",
                )
            return (b"", {})

        with (
            patch(
                "tools.disable_legacy_workflows._list_all_workflows",
                return_value=mock_workflows,
            ),
            patch(
                "tools.disable_legacy_workflows._http_request",
                side_effect=mock_http_request,
            ),
            patch(
                "tools.disable_legacy_workflows.CANONICAL_WORKFLOW_FILES",
                set(),
            ),
        ):
            result = disable_legacy_workflows(
                repository="test/repo",
                token="fake-token",
                dry_run=False,
            )

        assert "Good Workflow" in result["disabled"]
        assert len(result["skipped"]) == 1
        assert "Bad Workflow" in result["skipped"][0]
        assert "(unsupported)" in result["skipped"][0]

    def test_empty_workflow_list(self) -> None:
        """Test behavior with no workflows to process."""
        with (
            patch(
                "tools.disable_legacy_workflows._list_all_workflows",
                return_value=[],
            ),
            patch(
                "tools.disable_legacy_workflows._http_request",
                return_value=(b"", {}),
            ),
            patch(
                "tools.disable_legacy_workflows.CANONICAL_WORKFLOW_FILES",
                set(),
            ),
        ):
            result = disable_legacy_workflows(
                repository="test/repo",
                token="fake-token",
                dry_run=True,
            )

        assert result == {"disabled": [], "kept": [], "skipped": []}

    def test_keeps_workflows_by_stem_match(self) -> None:
        """Test that workflows are matched by stem (filename without extension)."""
        mock_workflows = [
            {"id": 1, "name": "Test CI", "path": ".github/workflows/ci.yml"},
        ]

        with (
            patch(
                "tools.disable_legacy_workflows._list_all_workflows",
                return_value=mock_workflows,
            ),
            patch(
                "tools.disable_legacy_workflows._http_request",
                return_value=(b"", {}),
            ),
            patch(
                "tools.disable_legacy_workflows.CANONICAL_WORKFLOW_FILES",
                {"ci.yml"},
            ),
        ):
            result = disable_legacy_workflows(
                repository="test/repo",
                token="fake-token",
                dry_run=True,
            )

        assert "Test CI" in result["kept"]
        assert result["disabled"] == []

    def test_workflow_without_name_field(self) -> None:
        """Test handling of workflows without a name field."""
        mock_workflows = [
            {"id": 1, "path": ".github/workflows/unnamed.yml"},
        ]

        with (
            patch(
                "tools.disable_legacy_workflows._list_all_workflows",
                return_value=mock_workflows,
            ),
            patch(
                "tools.disable_legacy_workflows._http_request",
                return_value=(b"", {}),
            ),
            patch(
                "tools.disable_legacy_workflows.CANONICAL_WORKFLOW_FILES",
                set(),
            ),
        ):
            result = disable_legacy_workflows(
                repository="test/repo",
                token="fake-token",
                dry_run=True,
            )

        # Should use empty string for name
        assert "" in result["disabled"]

    def test_workflow_without_path_field(self) -> None:
        """Test handling of workflows without a path field."""
        mock_workflows = [
            {"id": 1, "name": "Pathless Workflow"},
        ]

        with (
            patch(
                "tools.disable_legacy_workflows._list_all_workflows",
                return_value=mock_workflows,
            ),
            patch(
                "tools.disable_legacy_workflows._http_request",
                return_value=(b"", {}),
            ),
            patch(
                "tools.disable_legacy_workflows.CANONICAL_WORKFLOW_FILES",
                set(),
            ),
        ):
            result = disable_legacy_workflows(
                repository="test/repo",
                token="fake-token",
                dry_run=True,
            )

        # Should use empty string for path, resulting in empty stem
        assert "Pathless Workflow" in result["disabled"]

    def test_dry_run_does_not_make_http_requests(self) -> None:
        """Test that dry-run mode does not make actual HTTP requests."""
        mock_workflows = [
            {"id": 1, "name": "Test Workflow", "path": ".github/workflows/test.yml"},
        ]

        with (
            patch(
                "tools.disable_legacy_workflows._list_all_workflows",
                return_value=mock_workflows,
            ),
            patch(
                "tools.disable_legacy_workflows._http_request",
                return_value=(b"", {}),
            ) as mock_request,
            patch(
                "tools.disable_legacy_workflows.CANONICAL_WORKFLOW_FILES",
                set(),
            ),
        ):
            result = disable_legacy_workflows(
                repository="test/repo",
                token="fake-token",
                dry_run=True,
            )

        assert "Test Workflow" in result["disabled"]
        # _list_all_workflows is called, but _http_request should not be
        mock_request.assert_not_called()

    def test_non_dry_run_makes_http_requests(self) -> None:
        """Test that non-dry-run mode makes HTTP requests for disabling."""
        mock_workflows = [
            {"id": 1, "name": "Test Workflow", "path": ".github/workflows/test.yml"},
        ]

        with (
            patch(
                "tools.disable_legacy_workflows._list_all_workflows",
                return_value=mock_workflows,
            ),
            patch(
                "tools.disable_legacy_workflows._http_request",
                return_value=(b"", {}),
            ) as mock_request,
            patch(
                "tools.disable_legacy_workflows.CANONICAL_WORKFLOW_FILES",
                set(),
            ),
        ):
            result = disable_legacy_workflows(
                repository="test/repo",
                token="fake-token",
                dry_run=False,
            )

        assert "Test Workflow" in result["disabled"]
        # _http_request should be called once
        mock_request.assert_called_once()
