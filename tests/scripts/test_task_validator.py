"""Tests for scripts/langchain/task_validator.py."""

from __future__ import annotations

import sys
import types
from unittest.mock import Mock, call

import pytest
from scripts.langchain import task_validator as task_validator_module
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
    refine_flagged_tasks,
    triage_tasks,
    validate_no_items_lost,
    validate_tasks,
)
from scripts.langchain.trace_utils import TraceInfo


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
        assert _has_subjective_without_measurable("Run pytest tests/fast/test_api.py") is False
        assert _has_subjective_without_measurable("Make the UI clean/intuitive") is True
        assert (
            _has_subjective_without_measurable(
                "Update configuration in quality/Dockerfile for deployment defaults"
            )
            is False
        )
        assert _has_subjective_without_measurable("/quality/config") is False
        assert _has_subjective_without_measurable(".github/quality") is False
        assert _has_subjective_without_measurable("quality/clean.py") is False
        assert _has_subjective_without_measurable("src/quality/config") is False
        assert _has_subjective_without_measurable("clean/src_file") is False
        assert _has_subjective_without_measurable("quality.md") is False

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
            {"task": "Fix", "warnings": ["too_short"], "index": 0},
            {"task": "### Header", "warnings": ["is_header"], "index": 1},
            {"task": "Ensure quality", "warnings": ["subjective_language"], "index": 2},
        ]
        response = """- IMPROVE: Fix the authentication bug in login.py
- DROP: Section header
- IMPROVE: Add validation tests for output"""

        fates = _parse_refinement_response(response, flagged)
        assert len(fates) == 3
        assert fates[0].outcome == TaskOutcome.IMPROVED
        assert fates[1].outcome == TaskOutcome.DROPPED
        assert fates[2].outcome == TaskOutcome.IMPROVED
        assert [fate.original_index for fate in fates] == [0, 1, 2]

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

    def test_merge_with_audit_preserves_original_order(self) -> None:
        clean = ["Task A", "Task C"]
        clean_items = [{"task": "Task A", "index": 0}, {"task": "Task C", "index": 2}]
        refined = ["Task B improved"]
        fates = [
            TaskFate(
                original="Task B",
                outcome=TaskOutcome.IMPROVED,
                result="Task B improved",
                reason="improved",
                original_index=1,
            )
        ]

        final, audit = merge_with_audit(clean, refined, fates, 3, clean_items)
        assert final == ["Task A", "Task B improved", "Task C"]
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

    def test_blank_tasks_filtered_before_audit(self) -> None:
        tasks = ["", "  ", "Create scripts/metrics.py with timing helpers"]
        result = validate_tasks(tasks, use_llm=False)

        assert result.tasks == ["Create scripts/metrics.py with timing helpers"]
        assert "1 input" in result.audit_summary
        assert "1 output" in result.audit_summary

    def test_all_blank_tasks_are_empty(self) -> None:
        result = validate_tasks(["", "  "], use_llm=False)

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

    def test_mixed_tasks_preserve_order_without_llm(self) -> None:
        tasks = [
            "Create scripts/metrics.py with timing functions",
            "Fix",
            "Add unit tests for metrics collection",
            "### Validation",
        ]

        result = validate_tasks(tasks, use_llm=False)

        assert result.tasks == tasks

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

    def test_refine_flagged_tasks_empty_returns_trace_shape(self) -> None:
        refined, fates, provider, trace = refine_flagged_tasks([])

        assert refined == []
        assert fates == []
        assert provider is None
        assert trace.available is False

    def test_no_llm_refinement_preserves_task_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            task_validator_module,
            "_get_llm_client",
            lambda force_openai=False: None,
        )
        tasks = [
            "Create scripts/metrics.py with timing functions",
            "Fix",
            "Add unit tests for metrics collection",
        ]

        result = validate_tasks(tasks, use_llm=True)

        assert result.tasks == tasks
        assert result.fates[0].original_index == 1

    def test_blank_filtering_preserves_original_input_indexes(self) -> None:
        tasks = [
            "",
            "Create scripts/metrics.py with timing functions",
            "  ",
            "Fix",
            "Add unit tests for metrics collection",
        ]

        result = validate_tasks(tasks, use_llm=False)

        assert result.tasks == [
            "Create scripts/metrics.py with timing functions",
            "Fix",
            "Add unit tests for metrics collection",
        ]
        assert result.fates[0].original_index == 3
        assert "3 input" in result.audit_summary


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


@pytest.fixture
def refinement_boundary(monkeypatch):
    """Replace only the optional prompt SDK and provider invocation boundary."""

    class Prompt:
        def __init__(self, text):
            self.text = text

        def __or__(self, client):
            return (self.text, client)

    prompts = types.ModuleType("langchain_core.prompts")
    prompts.ChatPromptTemplate = types.SimpleNamespace(from_template=Prompt)
    core = types.ModuleType("langchain_core")
    core.prompts = prompts
    monkeypatch.setitem(sys.modules, "langchain_core", core)
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", prompts)
    primary, fallback = object(), object()
    select = Mock(return_value=(primary, "github-models"))
    invoke = Mock()
    monkeypatch.setattr(task_validator_module, "_get_llm_client", select)
    monkeypatch.setattr(task_validator_module, "invoke_with_trace", invoke)
    return primary, fallback, select, invoke


@pytest.mark.parametrize("message_object", [False, True], ids=["text", "message"])
def test_refinement_round_trip_preserves_order_fates_and_trace(refinement_boundary, message_object):
    primary, _, select, invoke = refinement_boundary
    text = "Decisions:\n- IMPROVE: Fix the login bug in auth.py\n- DROP: Section header"
    response = types.SimpleNamespace(content=text) if message_object else text
    trace = TraceInfo("trace-123", "https://example.test/traces/trace-123")
    invoke.return_value = response, trace
    clean = "Add unit tests for the authentication module"

    result = validate_tasks(["", "Fix", clean, "### Tasks"], context="Repair login")

    assert result.tasks == ["Fix the login bug in auth.py", clean]
    assert result.to_dict() == {
        "tasks": ["Fix the login bug in auth.py", clean],
        "fates": [
            {
                "original": "Fix",
                "outcome": "improved",
                "result": "Fix the login bug in auth.py",
                "reason": "LLM improved for actionability",
                "warnings": ["too_short"],
                "original_index": 1,
            },
            {
                "original": "### Tasks",
                "outcome": "dropped",
                "result": None,
                "reason": "Section header",
                "warnings": ["too_short", "is_header"],
                "original_index": 3,
            },
        ],
        "audit_summary": (
            "Task validation: 3 input → 2 output. "
            "Clean: 1, Kept: 0, Improved: 1, Dropped: 1, Fallback: 0"
        ),
        "provider_used": "github-models",
        "langsmith_trace_id": trace.trace_id,
        "langsmith_trace_url": trace.trace_url,
    }
    select.assert_called_once_with()
    invoke.assert_called_once_with(
        (task_validator_module.PROMPT_PATH.read_text(encoding="utf-8").strip(), primary),
        {
            "flagged_items": (
                "1. Fix (warnings: too_short)\n" "2. ### Tasks (warnings: too_short, is_header)"
            ),
            "context": "Repair login",
        },
        operation="task_validator",
    )


def test_refinement_missing_prompt_dependency_keeps_originals(monkeypatch, refinement_boundary):
    _, _, select, invoke = refinement_boundary
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", None)
    flagged = [{"task": "Fix", "warnings": ["too_short"], "index": 4}]

    tasks, fates, provider, trace = refine_flagged_tasks(flagged)

    assert tasks == ["Fix"]
    assert [fate.to_dict() for fate in fates] == [
        {
            "original": "Fix",
            "outcome": "unprocessed",
            "result": "Fix",
            "reason": "LangChain unavailable; keeping original",
            "warnings": ["too_short"],
            "original_index": 4,
        }
    ]
    assert provider is None
    assert trace == TraceInfo()
    select.assert_called_once_with()
    invoke.assert_not_called()


def test_refinement_auth_fallback_retries_same_prompt_and_returns_fallback_trace(
    refinement_boundary,
):
    primary, fallback, select, invoke = refinement_boundary
    select.side_effect = [(primary, "github-models"), (fallback, "openai")]
    trace = TraceInfo("fallback-trace", "https://example.test/fallback")
    invoke.side_effect = [RuntimeError("GitHub MODELS HTTP 401"), ("KEEP: rewritten", trace)]

    tasks, fates, provider, actual_trace = refine_flagged_tasks([{"task": "Fix", "index": 2}])

    assert tasks == ["Fix"]
    assert fates == [TaskFate("Fix", TaskOutcome.KEPT, "Fix", "LLM confirmed valid", [], 2)]
    assert provider == "openai"
    assert actual_trace == trace
    assert select.call_args_list == [call(), call(force_openai=True)]
    prompt = task_validator_module.PROMPT_PATH.read_text(encoding="utf-8").strip()
    payload = {"flagged_items": "1. Fix", "context": "None"}
    assert invoke.call_args_list == [
        call((prompt, primary), payload, operation="task_validator"),
        call((prompt, fallback), payload, operation="task_validator"),
    ]


@pytest.mark.parametrize(
    ("provider", "message"),
    [
        ("github-models", "models HTTP 503"),
        ("github-models", "unrelated HTTP 401"),
        ("openai", "models HTTP 401"),
    ],
    ids=["non-auth", "non-models", "non-github"],
)
def test_refinement_unrelated_errors_propagate_without_fallback(
    refinement_boundary, provider, message
):
    primary, _, select, invoke = refinement_boundary
    select.return_value = primary, provider
    error = RuntimeError(message)
    invoke.side_effect = error

    with pytest.raises(RuntimeError) as caught:
        refine_flagged_tasks([{"task": "Fix"}])

    assert caught.value is error
    select.assert_called_once_with()
    assert invoke.call_count == 1


@pytest.mark.parametrize("fallback_available", [False, True], ids=["unavailable", "fails"])
def test_refinement_exhausted_fallback_preserves_error(refinement_boundary, fallback_available):
    primary, fallback, select, invoke = refinement_boundary
    initial_error = RuntimeError("models HTTP 401")
    fallback_error = RuntimeError("fallback unavailable")
    select.side_effect = [
        (primary, "github-models"),
        (fallback, "openai") if fallback_available else None,
    ]
    invoke.side_effect = [initial_error, fallback_error]

    with pytest.raises(RuntimeError) as caught:
        refine_flagged_tasks([{"task": "Fix"}])

    assert caught.value is (fallback_error if fallback_available else initial_error)
    assert select.call_args_list == [call(), call(force_openai=True)]
    assert invoke.call_count == (2 if fallback_available else 1)


@pytest.mark.parametrize("prompt_exists", [False, True], ids=["builtin", "file"])
def test_refinement_loads_prompt_from_file_or_builtin(
    tmp_path, monkeypatch, refinement_boundary, prompt_exists
):
    primary, _, _, invoke = refinement_boundary
    prompt = tmp_path / "refine.md"
    if prompt_exists:
        prompt.write_text("  Custom {flagged_items} for {context}\n", encoding="utf-8")
    monkeypatch.setattr(task_validator_module, "PROMPT_PATH", prompt)
    invoke.return_value = "KEEP: Fix", TraceInfo()

    tasks, _, _, _ = refine_flagged_tasks([{"task": "Fix"}])

    assert tasks == ["Fix"]
    expected = (
        "Custom {flagged_items} for {context}"
        if prompt_exists
        else task_validator_module.REFINEMENT_PROMPT
    )
    invoke.assert_called_once_with(
        (expected, primary),
        {"flagged_items": "1. Fix", "context": "None"},
        operation="task_validator",
    )
