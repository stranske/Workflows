"""Tests for analyze_codex_session CLI script."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Import functions directly for unit testing
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.analyze_codex_session import (
    extract_all_tasks_from_pr_body,
    extract_tasks_from_pr_body,
    update_pr_body_checkboxes,
)


class TestExtractTasksFromPRBody:
    """Tests for PR body task extraction."""

    def test_extracts_unchecked_tasks(self) -> None:
        pr_body = """
## Tasks

- [ ] Fix the bug
- [ ] Add tests
- [x] Update docs
"""
        tasks = extract_tasks_from_pr_body(pr_body)
        assert tasks == ["Fix the bug", "Add tests"]

    def test_handles_mixed_indentation(self) -> None:
        pr_body = """
- [ ] Task 1
  - [ ] Subtask 1a
    - [ ] Sub-subtask
- [ ] Task 2
"""
        tasks = extract_tasks_from_pr_body(pr_body)
        assert "Task 1" in tasks
        assert "Subtask 1a" in tasks
        assert "Task 2" in tasks

    def test_handles_uppercase_x(self) -> None:
        pr_body = """
- [X] Completed with uppercase
- [ ] Still pending
"""
        tasks = extract_tasks_from_pr_body(pr_body)
        assert tasks == ["Still pending"]

    def test_empty_body_returns_empty_list(self) -> None:
        assert extract_tasks_from_pr_body("") == []

    def test_no_checkboxes_returns_empty_list(self) -> None:
        pr_body = """
## Description
This PR fixes a bug.

## Notes
- Item 1
- Item 2
"""
        assert extract_tasks_from_pr_body(pr_body) == []

    def test_extracts_from_multiple_sections(self) -> None:
        pr_body = """
## Tasks
- [ ] Task from tasks section

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
"""
        tasks = extract_tasks_from_pr_body(pr_body)
        assert len(tasks) == 3
        assert "Task from tasks section" in tasks
        assert "Criterion 1" in tasks


class TestExtractAllTasksFromPRBody:
    """Tests for extracting all tasks with status."""

    def test_extracts_all_with_status(self) -> None:
        pr_body = """
- [ ] Unchecked task
- [x] Checked task
- [X] Also checked
"""
        tasks = extract_all_tasks_from_pr_body(pr_body)
        assert tasks == {
            "Unchecked task": False,
            "Checked task": True,
            "Also checked": True,
        }


class TestUpdatePRBodyCheckboxes:
    """Tests for checkbox update logic."""

    def test_checks_completed_task(self) -> None:
        pr_body = "- [ ] Fix the bug\n- [ ] Add tests"
        updated = update_pr_body_checkboxes(pr_body, ["Fix the bug"])
        assert "- [x] Fix the bug" in updated
        assert "- [ ] Add tests" in updated

    def test_preserves_already_checked(self) -> None:
        pr_body = "- [x] Already done\n- [ ] New task"
        updated = update_pr_body_checkboxes(pr_body, ["New task"])
        assert "- [x] Already done" in updated
        assert "- [x] New task" in updated

    def test_handles_special_characters_in_task(self) -> None:
        pr_body = "- [ ] Fix bug (issue #123)"
        updated = update_pr_body_checkboxes(pr_body, ["Fix bug (issue #123)"])
        assert "- [x] Fix bug (issue #123)" in updated

    def test_handles_no_matches(self) -> None:
        pr_body = "- [ ] Task A"
        updated = update_pr_body_checkboxes(pr_body, ["Nonexistent task"])
        assert updated == pr_body

    def test_preserves_indentation(self) -> None:
        pr_body = "  - [ ] Indented task"
        updated = update_pr_body_checkboxes(pr_body, ["Indented task"])
        assert "  - [x] Indented task" in updated


class TestCLIScript:
    """Integration tests for the CLI script."""

    @pytest.fixture
    def sample_session_file(self, tmp_path: Path) -> Path:
        """Create a sample JSONL session file."""
        session_content = """{"type": "thread.started", "thread_id": "test123"}
{"type": "turn.started", "turn_id": "turn1"}
{"type": "item.completed", "item_type": "agent_message", "content": "I have fixed the bug in calculator.py. The tests now pass."}
{"type": "item.completed", "item_type": "command_execution", "command": "pytest", "exit_code": 0}
{"type": "turn.completed", "turn_id": "turn1"}
"""
        session_file = tmp_path / "session.jsonl"
        session_file.write_text(session_content)
        return session_file

    @pytest.fixture
    def sample_pr_body_file(self, tmp_path: Path) -> Path:
        """Create a sample PR body file."""
        pr_body = """## Tasks
- [ ] Fix the bug
- [ ] Add tests
- [ ] Update documentation
"""
        pr_body_file = tmp_path / "pr_body.md"
        pr_body_file.write_text(pr_body)
        return pr_body_file

    def test_cli_runs_with_task_args(self, sample_session_file: Path, tmp_path: Path) -> None:
        """Test CLI with --tasks argument."""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/analyze_codex_session.py",
                "--session-file",
                str(sample_session_file),
                "--tasks",
                "Fix the bug",
                "Add tests",
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        # Should succeed (exit 0)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        # Output should be valid JSON
        output = json.loads(result.stdout)
        assert "provider" in output
        assert "confidence" in output

    def test_cli_runs_with_pr_body_file(
        self, sample_session_file: Path, sample_pr_body_file: Path
    ) -> None:
        """Test CLI with --pr-body-file argument."""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/analyze_codex_session.py",
                "--session-file",
                str(sample_session_file),
                "--pr-body-file",
                str(sample_pr_body_file),
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_cli_returns_2_for_missing_session(self, tmp_path: Path) -> None:
        """Test CLI returns exit code 2 for missing session file."""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/analyze_codex_session.py",
                "--session-file",
                str(tmp_path / "nonexistent.jsonl"),
                "--tasks",
                "Some task",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        assert result.returncode == 2

    def test_cli_markdown_output(self, sample_session_file: Path, tmp_path: Path) -> None:
        """Test CLI with markdown output format."""
        result = subprocess.run(
            [
                sys.executable,
                "scripts/analyze_codex_session.py",
                "--session-file",
                str(sample_session_file),
                "--tasks",
                "Fix the bug",
                "--output",
                "markdown",
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        assert result.returncode == 0
        assert "**Analysis Summary**" in result.stdout

    def test_cli_update_pr_body_option(
        self, sample_session_file: Path, sample_pr_body_file: Path, tmp_path: Path
    ) -> None:
        """Test CLI with --update-pr-body option."""
        updated_file = tmp_path / "updated_body.md"

        # Mock the LLM to return a known completion
        with patch("tools.llm_provider.get_llm_provider") as mock_provider:
            from tools.llm_provider import RegexFallbackProvider

            mock_provider.return_value = RegexFallbackProvider()

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/analyze_codex_session.py",
                    "--session-file",
                    str(sample_session_file),
                    "--pr-body-file",
                    str(sample_pr_body_file),
                    "--output",
                    "json",
                    "--update-pr-body",
                    "--updated-body-file",
                    str(updated_file),
                ],
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent.parent.parent,
            )

            assert result.returncode == 0
