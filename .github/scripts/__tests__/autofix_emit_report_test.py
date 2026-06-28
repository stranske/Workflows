"""Tests for autofix_emit_report.py module."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "autofix_emit_report.py"
SPEC = importlib.util.spec_from_file_location("autofix_emit_report", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
autofix_emit_report = importlib.util.module_from_spec(SPEC)
sys.modules["autofix_emit_report"] = autofix_emit_report
SPEC.loader.exec_module(autofix_emit_report)

AutofixContext = autofix_emit_report.AutofixContext
build_context = autofix_emit_report.build_context
build_report = autofix_emit_report.build_report
load_enriched = autofix_emit_report.load_enriched
write_report = autofix_emit_report.write_report


class TestAutofixContextFileList:
    """Tests for AutofixContext.file_list trimming blank lines."""

    def test_file_list_trims_blank_lines(self) -> None:
        """file_list property trims blank lines from file_list_raw."""
        ctx = AutofixContext(
            output_path=Path("output.json"),
            enriched_path=Path("enriched.json"),
            pr_number="123",
            mode="fix",
            changed="10",
            remaining="5",
            new="2",
            file_list_raw="file1.py\n\nfile2.py\n\t\nfile3.py\r\n",
        )

        result = ctx.file_list
        assert result == ["file1.py", "file2.py", "file3.py"]

    def test_file_list_handles_empty_string(self) -> None:
        """file_list property handles empty string."""
        ctx = AutofixContext(
            output_path=Path("output.json"),
            enriched_path=Path("enriched.json"),
            pr_number="123",
            mode="fix",
            changed="10",
            remaining="5",
            new="2",
            file_list_raw="",
        )

        result = ctx.file_list
        assert result == []

    def test_file_list_handles_only_whitespace(self) -> None:
        """file_list property handles only whitespace."""
        ctx = AutofixContext(
            output_path=Path("output.json"),
            enriched_path=Path("enriched.json"),
            pr_number="123",
            mode="fix",
            changed="10",
            remaining="5",
            new="2",
            file_list_raw="   \n\t\n  \t  \n",
        )

        result = ctx.file_list
        assert result == []

    def test_file_list_preserves_non_empty_lines(self) -> None:
        """file_list property preserves non-empty lines with spaces."""
        ctx = AutofixContext(
            output_path=Path("output.json"),
            enriched_path=Path("enriched.json"),
            pr_number="123",
            mode="fix",
            changed="10",
            remaining="5",
            new="2",
            file_list_raw="  file1.py  \n\tfile2.py\t\n  file3.py  ",
        )

        result = ctx.file_list
        assert result == ["file1.py", "file2.py", "file3.py"]


class TestLoadEnriched:
    """Tests for load_enriched() function."""

    def test_load_enriched_missing_file(self, tmp_path: Path) -> None:
        """load_enriched returns None for missing file."""
        missing_path = tmp_path / "nonexistent.json"
        result = load_enriched(missing_path)
        assert result is None

    def test_load_enriched_invalid_json(self, tmp_path: Path) -> None:
        """load_enriched returns None for invalid JSON."""
        invalid_path = tmp_path / "invalid.json"
        invalid_path.write_text("{ invalid json }", encoding="utf-8")

        result = load_enriched(invalid_path)
        assert result is None

    def test_load_enriched_non_dict(self, tmp_path: Path) -> None:
        """load_enriched returns None for non-dict JSON."""
        non_dict_path = tmp_path / "non_dict.json"
        non_dict_path.write_text("[1, 2, 3]", encoding="utf-8")

        result = load_enriched(non_dict_path)
        assert result is None

    def test_load_enriched_valid_dict(self, tmp_path: Path) -> None:
        """load_enriched returns dict for valid JSON dict."""
        valid_path = tmp_path / "valid.json"
        test_data = {"key": "value", "number": 42}
        valid_path.write_text(json.dumps(test_data), encoding="utf-8")

        result = load_enriched(valid_path)
        assert result == test_data

    def test_load_enriched_empty_dict(self, tmp_path: Path) -> None:
        """load_enriched returns empty dict for empty JSON dict."""
        empty_path = tmp_path / "empty.json"
        empty_path.write_text("{}", encoding="utf-8")

        result = load_enriched(empty_path)
        assert result == {}

    def test_load_enriched_unicode_content(self, tmp_path: Path) -> None:
        """load_enriched handles unicode content."""
        unicode_path = tmp_path / "unicode.json"
        test_data = {"message": "Hello 世界 🌍"}
        unicode_path.write_text(json.dumps(test_data), encoding="utf-8")

        result = load_enriched(unicode_path)
        assert result == test_data


class TestBuildReport:
    """Tests for build_report() function."""

    def test_build_report_with_enriched_report(self, tmp_path: Path) -> None:
        """build_report with enriched report adds pull_request and timestamp_utc."""
        enriched_path = tmp_path / "enriched.json"
        enriched_data = {"existing_key": "existing_value", "issues": ["issue1"]}
        enriched_path.write_text(json.dumps(enriched_data), encoding="utf-8")

        ctx = AutofixContext(
            output_path=tmp_path / "output.json",
            enriched_path=enriched_path,
            pr_number="456",
            mode="fix",
            changed="10",
            remaining="5",
            new="2",
            file_list_raw="file1.py\nfile2.py",
        )

        # Mock datetime.now to return a fixed time
        fixed_time = datetime(2026, 6, 28, 12, 30, 45, tzinfo=UTC)
        with patch("autofix_emit_report.datetime") as mock_datetime:
            mock_datetime.now.return_value = fixed_time
            mock_datetime.UTC = UTC

            result = build_report(ctx)

        # Check that enriched data is preserved and new fields are added
        assert result["existing_key"] == "existing_value"
        assert result["issues"] == ["issue1"]
        assert result["pull_request"] == "456"
        assert result["timestamp_utc"] == "2026-06-28T12:30:45Z"

    def test_build_report_fallback_without_enriched(self, tmp_path: Path) -> None:
        """build_report without enriched report returns fallback structure."""
        ctx = AutofixContext(
            output_path=tmp_path / "output.json",
            enriched_path=tmp_path / "nonexistent.json",
            pr_number=None,
            mode="fix",
            changed="10",
            remaining="5",
            new="2",
            file_list_raw="file1.py\n\nfile2.py\n",
        )

        result = build_report(ctx)

        # Check fallback structure
        assert result["mode"] == "fix"
        assert result["changed"] == "10"
        assert result["remaining_issues"] == "5"
        assert result["new_issues"] == "2"
        assert result["file_list"] == ["file1.py", "file2.py"]
        # Should not have enriched-only fields
        assert "pull_request" not in result
        assert "timestamp_utc" not in result

    def test_build_report_fallback_with_empty_enriched(self, tmp_path: Path) -> None:
        """build_report with empty enriched file updates the empty dict with new fields."""
        enriched_path = tmp_path / "empty.json"
        enriched_path.write_text("{}", encoding="utf-8")

        ctx = AutofixContext(
            output_path=tmp_path / "output.json",
            enriched_path=enriched_path,
            pr_number="789",
            mode="fix",
            changed="10",
            remaining="5",
            new="2",
            file_list_raw="file1.py",
        )

        result = build_report(ctx)

        # Empty dict is still a valid enriched report, so it should update with new fields
        assert result["pull_request"] == "789"
        assert "timestamp_utc" in result
        # Should not have fallback fields since enriched report was valid (empty dict)
        assert "mode" not in result
        assert "changed" not in result


class TestWriteReport:
    """Tests for write_report() function."""

    def test_write_report_formatting(self, tmp_path: Path) -> None:
        """write_report writes JSON with indent=2, sort_keys=True, and trailing newline."""
        destination = tmp_path / "output.json"
        report = {"b_key": "b_value", "a_key": "a_value", "nested": {"z": 1, "a": 2}}

        write_report(report, destination)

        content = destination.read_text(encoding="utf-8")
        # Check that it ends with newline
        assert content.endswith("\n")

        # Parse and verify structure
        parsed = json.loads(content)
        assert parsed == report

        # Check that keys are sorted (sort_keys=True effect)
        # The JSON should have sorted keys in the output
        lines = content.strip().split("\n")
        # First non-brace line should start with the alphabetically first key
        assert lines[0] == "{"
        # Find first key line
        for line in lines[1:]:
            if line.strip().startswith('"'):
                first_key = line.strip().split(":")[0].strip('"')
                break
        assert first_key == "a_key"  # Should be sorted

    def test_write_report_empty_dict(self, tmp_path: Path) -> None:
        """write_report handles empty dict."""
        destination = tmp_path / "empty.json"
        report = {}

        write_report(report, destination)

        content = destination.read_text(encoding="utf-8")
        assert content == "{}\n"

    def test_write_report_nested_structure(self, tmp_path: Path) -> None:
        """write_report handles nested structures."""
        destination = tmp_path / "nested.json"
        report = {
            "level1": {
                "level2": {"level3": ["a", "b", "c"]},
                "sibling": "value",
            },
            "top_key": "top_value",
        }

        write_report(report, destination)

        content = destination.read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert parsed == report


class TestBuildContext:
    """Tests for build_context() function."""

    def test_build_context_default_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """build_context uses default values when env vars are not set."""
        # Clear all relevant environment variables
        for var in [
            "AUTOFIX_REPORT",
            "AUTOFIX_REPORT_ENRICHED",
            "PR_NUMBER",
            "REPORT_MODE",
            "REPORT_CHANGED",
            "REPORT_REMAINING",
            "REPORT_NEW",
            "REPORT_FILE_LIST",
        ]:
            monkeypatch.delenv(var, raising=False)

        ctx = build_context()

        assert ctx.output_path == Path("autofix_report.json")
        assert ctx.enriched_path == Path("autofix_report_enriched.json")
        assert ctx.pr_number is None
        assert ctx.mode == ""
        assert ctx.changed == ""
        assert ctx.remaining == ""
        assert ctx.new == ""
        assert ctx.file_list_raw == ""

    def test_build_context_with_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """build_context reads values from environment variables."""
        monkeypatch.setenv("AUTOFIX_REPORT", "custom_report.json")
        monkeypatch.setenv("AUTOFIX_REPORT_ENRICHED", "custom_enriched.json")
        monkeypatch.setenv("PR_NUMBER", "999")
        monkeypatch.setenv("REPORT_MODE", "dry-run")
        monkeypatch.setenv("REPORT_CHANGED", "15")
        monkeypatch.setenv("REPORT_REMAINING", "3")
        monkeypatch.setenv("REPORT_NEW", "1")
        monkeypatch.setenv("REPORT_FILE_LIST", "src/file1.py\nsrc/file2.py")

        ctx = build_context()

        assert ctx.output_path == Path("custom_report.json")
        assert ctx.enriched_path == Path("custom_enriched.json")
        assert ctx.pr_number == "999"
        assert ctx.mode == "dry-run"
        assert ctx.changed == "15"
        assert ctx.remaining == "3"
        assert ctx.new == "1"
        assert ctx.file_list_raw == "src/file1.py\nsrc/file2.py"

    def test_build_context_partial_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """build_context uses defaults for missing env vars."""
        monkeypatch.setenv("PR_NUMBER", "123")
        monkeypatch.setenv("REPORT_MODE", "fix")
        # Leave others unset

        ctx = build_context()

        assert ctx.pr_number == "123"
        assert ctx.mode == "fix"
        assert ctx.changed == ""  # default
        assert ctx.remaining == ""  # default
        assert ctx.new == ""  # default
        assert ctx.file_list_raw == ""  # default


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_full_workflow_with_enriched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test full workflow: build_context -> build_report -> write_report with enriched."""
        # Set up environment
        monkeypatch.setenv("AUTOFIX_REPORT", "output.json")
        monkeypatch.setenv("AUTOFIX_REPORT_ENRICHED", "enriched.json")
        monkeypatch.setenv("PR_NUMBER", "42")
        monkeypatch.setenv("REPORT_MODE", "fix")
        monkeypatch.setenv("REPORT_CHANGED", "5")
        monkeypatch.setenv("REPORT_REMAINING", "2")
        monkeypatch.setenv("REPORT_NEW", "1")
        monkeypatch.setenv("REPORT_FILE_LIST", "file1.py\nfile2.py")

        # Create enriched file
        enriched_data = {"enriched_field": "enriched_value"}
        enriched_path = tmp_path / "enriched.json"
        enriched_path.write_text(json.dumps(enriched_data), encoding="utf-8")

        # Change to temp directory
        original_cwd = Path.cwd()
        monkeypatch.chdir(tmp_path)

        try:
            ctx = build_context()
            # Update paths to be absolute in tmp_path
            ctx.output_path = tmp_path / "output.json"
            ctx.enriched_path = enriched_path

            # Mock datetime for consistent timestamp
            fixed_time = datetime(2026, 6, 28, 10, 0, 0, tzinfo=UTC)
            with patch("autofix_emit_report.datetime") as mock_datetime:
                mock_datetime.now.return_value = fixed_time
                mock_datetime.UTC = UTC

                report = build_report(ctx)
                write_report(report, ctx.output_path)

            # Verify output
            output_content = (tmp_path / "output.json").read_text(encoding="utf-8")
            parsed = json.loads(output_content)

            assert parsed["enriched_field"] == "enriched_value"
            assert parsed["pull_request"] == "42"
            assert parsed["timestamp_utc"] == "2026-06-28T10:00:00Z"

        finally:
            monkeypatch.chdir(original_cwd)

    def test_full_workflow_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test full workflow with fallback when no enriched file exists."""
        # Set up environment
        monkeypatch.setenv("AUTOFIX_REPORT", "output.json")
        monkeypatch.setenv("AUTOFIX_REPORT_ENRICHED", "missing_enriched.json")
        monkeypatch.delenv("PR_NUMBER", raising=False)  # Explicitly None
        monkeypatch.setenv("REPORT_MODE", "fix")
        monkeypatch.setenv("REPORT_CHANGED", "5")
        monkeypatch.setenv("REPORT_REMAINING", "2")
        monkeypatch.setenv("REPORT_NEW", "1")
        monkeypatch.setenv("REPORT_FILE_LIST", "file1.py\n\nfile2.py\n")

        # Change to temp directory
        original_cwd = Path.cwd()
        monkeypatch.chdir(tmp_path)

        try:
            ctx = build_context()
            # Update paths to be absolute in tmp_path
            ctx.output_path = tmp_path / "output.json"
            ctx.enriched_path = tmp_path / "missing_enriched.json"

            report = build_report(ctx)
            write_report(report, ctx.output_path)

            # Verify output
            output_content = (tmp_path / "output.json").read_text(encoding="utf-8")
            parsed = json.loads(output_content)

            # Should use fallback structure
            assert parsed["mode"] == "fix"
            assert parsed["changed"] == "5"
            assert parsed["remaining_issues"] == "2"
            assert parsed["new_issues"] == "1"
            assert parsed["file_list"] == ["file1.py", "file2.py"]
            assert "pull_request" not in parsed
            assert "timestamp_utc" not in parsed

        finally:
            monkeypatch.chdir(original_cwd)
