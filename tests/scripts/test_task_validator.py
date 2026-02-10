"""Tests for scripts/langchain/task_validator.py."""

from __future__ import annotations

import pytest
from scripts.langchain.task_validator import (
    TaskFate,
    TaskOutcome,
    ValidationResult,
    _has_expansion_prefix,
    _has_subjective_without_measurable,
    _is_header_syntax,
    _is_punctuation_fragment,
    _is_too_short,
    _looks_like_human_activity,
    _parse_refinement_response,
    merge_with_audit,
    triage_tasks,
    validate_no_items_lost,
    validate_tasks,
)


class TestHeuristicDetection:
    """Test individual heuristic detection functions."""

    def test_is_too_short(self) -> None:
        assert _is_too_short("Fix bug") is True
        assert _is_too_short("Fix the bug") is True
        assert _is_too_short("Fix the login bug in auth") is False

    def test_is_header_syntax(self) -> None:
        assert _is_header_syntax("### Input Sanitization") is True
        assert _is_header_syntax("## Tasks") is True
        assert _is_header_syntax("# Header") is True
        assert _is_header_syntax("Create file.py") is False
        assert _is_header_syntax("This has # in middle") is False

    def test_has_subjective_without_measurable(self) -> None:
        assert _has_subjective_without_measurable("Ensure clean code") is True
        assert _has_subjective_without_measurable("Ensure quality") is True
        assert _has_subjective_without_measurable("Ensure tests pass") is False  # has "tests"
        assert _has_subjective_without_measurable("Create metrics file") is False

    def test_looks_like_human_activity(self) -> None:
        assert _looks_like_human_activity("Train staff on procedures") is True
        assert _looks_like_human_activity("Conduct session with team") is True
        assert _looks_like_human_activity("Obtain feedback from stakeholder") is True
        assert _looks_like_human_activity("Create training_data.py") is False
        assert _looks_like_human_activity("Add unit tests for module") is False

    def test_has_expansion_prefix(self) -> None:
        assert _has_expansion_prefix("Define scope for: something") is True
        assert _has_expansion_prefix("Implement focused slice for: X") is True
        assert _has_expansion_prefix("Validate focused slice for: Y") is True
        assert _has_expansion_prefix("Define approach for: Z") is True
        assert _has_expansion_prefix("Create new file") is False

    def test_is_punctuation_fragment(self) -> None:
        assert _is_punctuation_fragment(",;:.!?") is True
        assert _is_punctuation_fragment("   ") is True
        assert _is_punctuation_fragment("()") is True
        assert _is_punctuation_fragment("Create file") is False


class TestTriage:
    """Test triage_tasks function."""

    def test_clean_tasks_pass_through(self) -> None:
        tasks = [
            "Create scripts/metrics_collector.py with collect_timing function",
            "Add unit tests for MetricsCollector class",
            "Update workflow to call metrics collection step",
        ]
        result = triage_tasks(tasks)
        assert len(result["clean"]) == 3
        assert len(result["flagged"]) == 0

    def test_flagged_tasks_with_warnings(self) -> None:
        tasks = [
            "### Input Sanitization",  # header
            "Fix",  # too short
            "Ensure quality",  # subjective
            "Train staff on procedures",  # human activity
            "Define scope for: Define scope for: X",  # recursive prefix
        ]
        result = triage_tasks(tasks)
        assert len(result["clean"]) == 0
        assert len(result["flagged"]) == 5

        # Check warnings are attached
        for item in result["flagged"]:
            assert len(item["warnings"]) > 0

    def test_mixed_clean_and_flagged(self) -> None:
        tasks = [
            "Create utils.py file with helper functions",
            "### Header",
            "Add unit tests for the authentication module",
            "Ensure quality",
        ]
        result = triage_tasks(tasks)
        assert len(result["clean"]) == 2
        assert len(result["flagged"]) == 2

    def test_empty_tasks_filtered(self) -> None:
        tasks = ["", "  ", "Create file.py with utility functions"]
        result = triage_tasks(tasks)
        assert len(result["clean"]) == 1
        assert len(result["flagged"]) == 0


class TestParseRefinementResponse:
    """Test parsing of LLM refinement responses."""

    def test_parse_keep_response(self) -> None:
        flagged = [{"task": "Create metrics.py file", "warnings": ["too_short"]}]
        response = "- KEEP: Create metrics.py file"

        fates = _parse_refinement_response(response, flagged)
        assert len(fates) == 1
        assert fates[0].outcome == TaskOutcome.KEPT
        assert fates[0].result == "Create metrics.py file"

    def test_parse_improve_response(self) -> None:
        flagged = [{"task": "Ensure quality", "warnings": ["subjective_language"]}]
        response = "- IMPROVE: Add unit tests to validate output format"

        fates = _parse_refinement_response(response, flagged)
        assert len(fates) == 1
        assert fates[0].outcome == TaskOutcome.IMPROVED
        assert fates[0].result == "Add unit tests to validate output format"

    def test_parse_drop_response(self) -> None:
        flagged = [{"task": "### Header", "warnings": ["is_header"]}]
        response = "- DROP: Section header, not a task"

        fates = _parse_refinement_response(response, flagged)
        assert len(fates) == 1
        assert fates[0].outcome == TaskOutcome.DROPPED
        assert fates[0].result is None
        assert "header" in fates[0].reason.lower()

    def test_parse_multiple_responses(self) -> None:
        flagged = [
            {"task": "Fix", "warnings": ["too_short"]},
            {"task": "### Header", "warnings": ["is_header"]},
            {"task": "Ensure quality", "warnings": ["subjective_language"]},
        ]
        response = """- IMPROVE: Fix the authentication bug in login.py
- DROP: Section header
- IMPROVE: Add validation tests for output"""

        fates = _parse_refinement_response(response, flagged)
        assert len(fates) == 3
        assert fates[0].outcome == TaskOutcome.IMPROVED
        assert fates[1].outcome == TaskOutcome.DROPPED
        assert fates[2].outcome == TaskOutcome.IMPROVED

    def test_fallback_to_original_on_missing_response(self) -> None:
        flagged = [
            {"task": "Task A", "warnings": ["too_short"]},
            {"task": "Task B", "warnings": ["too_short"]},
        ]
        # LLM only responded to first item
        response = "- KEEP: Task A"

        fates = _parse_refinement_response(response, flagged)
        assert len(fates) == 2
        assert fates[0].outcome == TaskOutcome.KEPT
        assert fates[1].outcome == TaskOutcome.UNPROCESSED
        assert fates[1].result == "Task B"  # Original preserved


class TestAuditAndMerge:
    """Test audit and merge functions."""

    def test_validate_no_items_lost_passes(self) -> None:
        # 5 input = 3 kept + 2 dropped
        validate_no_items_lost(
            original_count=5,
            result_count=3,
            dropped_count=2,
        )  # Should not raise

    def test_validate_no_items_lost_raises(self) -> None:
        # 5 input but only 3 accounted for
        with pytest.raises(ValueError, match="Item loss detected"):
            validate_no_items_lost(
                original_count=5,
                result_count=2,
                dropped_count=1,
            )

    def test_merge_with_audit_success(self) -> None:
        clean = ["Task A", "Task B"]
        refined = ["Task C improved"]
        fates = [
            TaskFate(
                original="Task C",
                outcome=TaskOutcome.IMPROVED,
                result="Task C improved",
                reason="improved",
            )
        ]
        original_count = 3  # 2 clean + 1 flagged

        final, audit = merge_with_audit(clean, refined, fates, original_count)
        assert len(final) == 3
        assert "3 input" in audit
        assert "3 output" in audit

    def test_merge_with_audit_with_drops(self) -> None:
        clean = ["Task A"]
        refined = []  # Nothing from refinement kept
        fates = [
            TaskFate(
                original="### Header",
                outcome=TaskOutcome.DROPPED,
                result=None,
                reason="header",
            )
        ]
        original_count = 2

        final, audit = merge_with_audit(clean, refined, fates, original_count)
        assert len(final) == 1
        assert "Dropped: 1" in audit


class TestValidateTasks:
    """Test the main validate_tasks function."""

    def test_empty_tasks(self) -> None:
        result = validate_tasks([])
        assert result.tasks == []
        assert "No tasks" in result.audit_summary

    def test_all_clean_tasks(self) -> None:
        tasks = [
            "Create scripts/metrics.py with timing functions",
            "Add unit tests for metrics collection",
        ]
        result = validate_tasks(tasks, use_llm=False)
        assert len(result.tasks) == 2
        assert "All clean" in result.audit_summary

    def test_flagged_tasks_without_llm(self) -> None:
        tasks = [
            "Create metrics collector script in scripts directory",  # Clean
            "Fix",  # Too short - will be flagged
        ]
        result = validate_tasks(tasks, use_llm=False)

        # Without LLM, flagged items should be kept as UNPROCESSED
        assert len(result.tasks) == 2
        assert len(result.fates) == 1  # One flagged item
        assert result.fates[0].outcome == TaskOutcome.UNPROCESSED

    def test_no_silent_item_loss(self) -> None:
        """Verify that items are never silently dropped."""
        tasks = [
            "Good task",  # Will be flagged (too short)
            "Another task",  # Will be flagged (too short)
            "Create scripts/metrics.py with timing collection functions",  # Clean
        ]
        result = validate_tasks(tasks, use_llm=False)

        # All tasks should be in output (none dropped without LLM)
        assert len(result.tasks) == 3


class TestTaskFateSerialization:
    """Test TaskFate dataclass serialization."""

    def test_to_dict(self) -> None:
        fate = TaskFate(
            original="Original task",
            outcome=TaskOutcome.IMPROVED,
            result="Improved task",
            reason="Made actionable",
            warnings=["too_short"],
        )
        d = fate.to_dict()
        assert d["original"] == "Original task"
        assert d["outcome"] == "improved"
        assert d["result"] == "Improved task"
        assert d["reason"] == "Made actionable"
        assert d["warnings"] == ["too_short"]


class TestValidationResultSerialization:
    """Test ValidationResult dataclass serialization."""

    def test_to_dict(self) -> None:
        result = ValidationResult(
            tasks=["Task A", "Task B"],
            fates=[
                TaskFate(
                    original="Old",
                    outcome=TaskOutcome.KEPT,
                    result="Old",
                )
            ],
            audit_summary="2 input -> 2 output",
            provider_used="github-models",
        )
        d = result.to_dict()
        assert d["tasks"] == ["Task A", "Task B"]
        assert len(d["fates"]) == 1
        assert d["audit_summary"] == "2 input -> 2 output"
        assert d["provider_used"] == "github-models"
