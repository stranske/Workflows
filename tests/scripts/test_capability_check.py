"""Tests for scripts/langchain/capability_check.py."""

from __future__ import annotations

import json
import sys
import types
from io import StringIO
from typing import Any
from unittest import mock

import pytest
from scripts.langchain.capability_check import (
    AGENT_CAPABILITY_CHECK_PROMPT,
    CapabilityCheckResult,
    _coerce_dict_list,
    _coerce_list,
    _extract_json_payload,
    _normalize_result,
    _normalize_tasks_input,
    _parse_tasks_from_text,
    _prepare_prompt_values,
    _strip_checkbox,
    classify_capabilities,
    main,
)


class TestCapabilityCheckResult:
    """Tests for the CapabilityCheckResult dataclass."""

    def test_to_dict_includes_all_fields(self) -> None:
        result = CapabilityCheckResult(
            actionable_tasks=["task1", "task2"],
            partial_tasks=[{"task": "partial", "limitation": "reason"}],
            blocked_tasks=[{"task": "blocked", "reason": "why", "suggested_action": "do this"}],
            recommendation="PROCEED",
            human_actions_needed=["review this"],
            provider_used="github-models",
        )
        data = result.to_dict()
        assert data["actionable_tasks"] == ["task1", "task2"]
        assert data["partial_tasks"] == [{"task": "partial", "limitation": "reason"}]
        assert data["blocked_tasks"] == [
            {"task": "blocked", "reason": "why", "suggested_action": "do this"}
        ]
        assert data["recommendation"] == "PROCEED"
        assert data["human_actions_needed"] == ["review this"]
        assert data["provider_used"] == "github-models"

    def test_to_dict_handles_none_provider(self) -> None:
        result = CapabilityCheckResult(
            actionable_tasks=[],
            partial_tasks=[],
            blocked_tasks=[],
            recommendation="REVIEW_NEEDED",
            human_actions_needed=[],
            provider_used=None,
        )
        data = result.to_dict()
        assert data["provider_used"] is None


class TestPreparePromptValues:
    """Tests for _prepare_prompt_values."""

    def test_formats_tasks_as_bullet_list(self) -> None:
        result = _prepare_prompt_values(["task1", "task2"], "criteria")
        assert result["tasks"] == "- task1\n- task2"
        assert result["acceptance"] == "criteria"

    def test_handles_empty_tasks(self) -> None:
        result = _prepare_prompt_values([], "criteria")
        assert result["tasks"] == "- (none)"

    def test_handles_empty_acceptance(self) -> None:
        result = _prepare_prompt_values(["task1"], "")
        assert result["acceptance"] == "(none)"

    def test_strips_whitespace_from_acceptance(self) -> None:
        result = _prepare_prompt_values(["task1"], "  criteria  \n")
        assert result["acceptance"] == "criteria"


class TestExtractJsonPayload:
    """Tests for _extract_json_payload."""

    def test_extracts_clean_json(self) -> None:
        text = '{"key": "value"}'
        assert _extract_json_payload(text) == '{"key": "value"}'

    def test_extracts_json_from_text(self) -> None:
        text = 'Here is the result:\n{"key": "value"}\nEnd of response.'
        assert _extract_json_payload(text) == '{"key": "value"}'

    def test_handles_nested_braces(self) -> None:
        text = '{"outer": {"inner": "value"}}'
        assert _extract_json_payload(text) == '{"outer": {"inner": "value"}}'

    def test_returns_none_for_no_json(self) -> None:
        assert _extract_json_payload("no json here") is None

    def test_returns_none_for_malformed(self) -> None:
        assert _extract_json_payload("{ incomplete") is None

    def test_returns_none_for_reversed_braces(self) -> None:
        assert _extract_json_payload("} reversed {") is None


class TestCoerceList:
    """Tests for _coerce_list."""

    def test_coerces_string_list(self) -> None:
        assert _coerce_list(["a", "b", "c"]) == ["a", "b", "c"]

    def test_strips_whitespace(self) -> None:
        assert _coerce_list(["  a  ", "b\n"]) == ["a", "b"]

    def test_filters_empty_strings(self) -> None:
        assert _coerce_list(["a", "", "  ", "b"]) == ["a", "b"]

    def test_filters_non_strings(self) -> None:
        assert _coerce_list(["a", 123, None, "b"]) == ["a", "b"]

    def test_returns_empty_for_non_list(self) -> None:
        assert _coerce_list("not a list") == []
        assert _coerce_list(None) == []
        assert _coerce_list(123) == []


class TestCoerceDictList:
    """Tests for _coerce_dict_list."""

    def test_coerces_valid_dicts(self) -> None:
        value = [{"task": "t1", "limitation": "l1"}]
        result = _coerce_dict_list(value, {"task", "limitation"})
        assert result == [{"task": "t1", "limitation": "l1"}]

    def test_filters_incomplete_dicts(self) -> None:
        value = [{"task": "t1"}, {"task": "t2", "limitation": "l2"}]
        result = _coerce_dict_list(value, {"task", "limitation"})
        assert result == [{"task": "t2", "limitation": "l2"}]

    def test_filters_non_dicts(self) -> None:
        value = ["not a dict", {"task": "t1", "limitation": "l1"}]
        result = _coerce_dict_list(value, {"task", "limitation"})
        assert result == [{"task": "t1", "limitation": "l1"}]

    def test_strips_whitespace(self) -> None:
        value = [{"task": "  t1  ", "limitation": "\nl1\n"}]
        result = _coerce_dict_list(value, {"task", "limitation"})
        assert result == [{"task": "t1", "limitation": "l1"}]

    def test_returns_empty_for_non_list(self) -> None:
        assert _coerce_dict_list("not a list", {"task"}) == []


class TestNormalizeResult:
    """Tests for _normalize_result."""

    def test_normalizes_valid_payload(self) -> None:
        payload: dict[str, Any] = {
            "actionable_tasks": ["task1"],
            "partial_tasks": [{"task": "p1", "limitation": "l1"}],
            "blocked_tasks": [{"task": "b1", "reason": "r1", "suggested_action": "s1"}],
            "recommendation": "PROCEED",
            "human_actions_needed": ["action1"],
        }
        result = _normalize_result(payload, "github-models")
        assert result.actionable_tasks == ["task1"]
        assert result.partial_tasks == [{"task": "p1", "limitation": "l1"}]
        assert result.blocked_tasks == [{"task": "b1", "reason": "r1", "suggested_action": "s1"}]
        assert result.recommendation == "PROCEED"
        assert result.human_actions_needed == ["action1"]
        assert result.provider_used == "github-models"

    def test_normalizes_recommendation_to_uppercase(self) -> None:
        result = _normalize_result({"recommendation": "proceed"}, None)
        assert result.recommendation == "PROCEED"

    def test_defaults_invalid_recommendation(self) -> None:
        result = _normalize_result({"recommendation": "INVALID"}, None)
        assert result.recommendation == "REVIEW_NEEDED"

    def test_defaults_missing_recommendation(self) -> None:
        result = _normalize_result({}, None)
        assert result.recommendation == "REVIEW_NEEDED"

    def test_handles_empty_payload(self) -> None:
        result = _normalize_result({}, None)
        assert result.actionable_tasks == []
        assert result.partial_tasks == []
        assert result.blocked_tasks == []
        assert result.human_actions_needed == []


class TestStripCheckbox:
    """Tests for _strip_checkbox."""

    def test_strips_unchecked_checkbox(self) -> None:
        assert _strip_checkbox("- [ ] task") == "task"

    def test_strips_checked_checkbox(self) -> None:
        assert _strip_checkbox("- [x] task") == "task"
        assert _strip_checkbox("- [X] task") == "task"

    def test_strips_plain_bullet(self) -> None:
        assert _strip_checkbox("- task") == "task"

    def test_strips_asterisk_bullet(self) -> None:
        assert _strip_checkbox("* task") == "task"

    def test_strips_plus_bullet(self) -> None:
        assert _strip_checkbox("+ task") == "task"

    def test_handles_leading_whitespace(self) -> None:
        assert _strip_checkbox("  - [ ] task") == "task"


class TestParseTasksFromText:
    """Tests for _parse_tasks_from_text."""

    def test_parses_bullet_list(self) -> None:
        text = "- task1\n- task2\n- task3"
        assert _parse_tasks_from_text(text) == ["task1", "task2", "task3"]

    def test_parses_indented_bullets(self) -> None:
        text = "  - task1\n\t* task2\n    + task3"
        assert _parse_tasks_from_text(text) == ["task1", "task2", "task3"]

    def test_parses_checkbox_list(self) -> None:
        text = "- [ ] task1\n- [x] task2"
        assert _parse_tasks_from_text(text) == ["task1", "task2"]

    def test_parses_checked_uppercase_box(self) -> None:
        text = "- [X] task1\n- [ ] task2"
        assert _parse_tasks_from_text(text) == ["task1", "task2"]

    def test_parses_mixed_bullets(self) -> None:
        text = "- task1\n* task2\n+ task3"
        assert _parse_tasks_from_text(text) == ["task1", "task2", "task3"]

    def test_ignores_non_bullet_lines(self) -> None:
        text = "# Header\n- task1\nParagraph text\n- task2"
        assert _parse_tasks_from_text(text) == ["task1", "task2"]

    def test_ignores_empty_lines(self) -> None:
        text = "- task1\n\n\n- task2"
        assert _parse_tasks_from_text(text) == ["task1", "task2"]

    def test_ignores_empty_bullets(self) -> None:
        text = "- task1\n- \n-\n- task2"
        assert _parse_tasks_from_text(text) == ["task1", "task2"]


class TestNormalizeTasksInput:
    """Tests for _normalize_tasks_input."""

    def test_returns_empty_for_none(self) -> None:
        assert _normalize_tasks_input(None) == []

    def test_parses_bullets_from_string(self) -> None:
        tasks = "- task1\n- task2"
        assert _normalize_tasks_input(tasks) == ["task1", "task2"]


class TestClassifyCapabilities:
    """Tests for classify_capabilities."""

    def _install_fake_langchain(
        self, monkeypatch: pytest.MonkeyPatch, mock_chain: mock.MagicMock
    ) -> None:
        mock_template = mock.MagicMock()
        mock_template.__or__ = mock.MagicMock(return_value=mock_chain)

        class FakeChatPromptTemplate:
            @staticmethod
            def from_template(_: str) -> Any:
                return mock_template

        fake_prompts = types.SimpleNamespace(ChatPromptTemplate=FakeChatPromptTemplate)
        fake_core = types.SimpleNamespace(prompts=fake_prompts)
        monkeypatch.setitem(sys.modules, "langchain_core", fake_core)
        monkeypatch.setitem(sys.modules, "langchain_core.prompts", fake_prompts)

    def test_returns_fallback_when_no_llm_client(self) -> None:
        with mock.patch("scripts.langchain.capability_check._get_llm_client", return_value=None):
            result = classify_capabilities(["task1"], "criteria")
            assert result.recommendation == "PROCEED"
            assert result.actionable_tasks == ["task1"]
            assert "LLM provider unavailable" in result.human_actions_needed
            assert result.provider_used is None

    def test_returns_fallback_when_langchain_core_missing(self) -> None:
        mock_client = mock.MagicMock()
        with mock.patch(
            "scripts.langchain.capability_check._get_llm_client",
            return_value=(mock_client, "github-models"),
        ):
            # Simulate langchain_core import failure
            import builtins

            original_import = builtins.__import__

            def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
                if name == "langchain_core.prompts":
                    raise ImportError("No module named 'langchain_core'")
                return original_import(name, *args, **kwargs)

            with mock.patch.object(builtins, "__import__", mock_import):
                result = classify_capabilities(["task1"], "criteria")
                assert result.recommendation == "PROCEED"
                assert result.actionable_tasks == ["task1"]
                assert result.provider_used == "github-models"
                assert "langchain-core not installed" in result.human_actions_needed

    def test_normalizes_tasks_when_langchain_core_missing(self) -> None:
        mock_client = mock.MagicMock()
        with mock.patch(
            "scripts.langchain.capability_check._get_llm_client",
            return_value=(mock_client, "github-models"),
        ):
            import builtins

            original_import = builtins.__import__

            def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
                if name == "langchain_core.prompts":
                    raise ImportError("No module named 'langchain_core'")
                return original_import(name, *args, **kwargs)

            with mock.patch.object(builtins, "__import__", mock_import):
                result = classify_capabilities("- task1\n- task2", "criteria")
                assert result.actionable_tasks == ["task1", "task2"]
                assert result.provider_used == "github-models"
                assert "langchain-core not installed" in result.human_actions_needed

    def test_invokes_chain_with_prompt_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_client = mock.MagicMock()
        mock_chain = mock.MagicMock()
        mock_response = mock.MagicMock()
        mock_response.content = json.dumps(
            {
                "actionable_tasks": ["task1"],
                "partial_tasks": [],
                "blocked_tasks": [],
                "recommendation": "proceed",
                "human_actions_needed": ["  review  "],
            }
        )
        mock_chain.invoke.return_value = mock_response

        self._install_fake_langchain(monkeypatch, mock_chain)

        with mock.patch(
            "scripts.langchain.capability_check._get_llm_client",
            return_value=(mock_client, "github-models"),
        ):
            result = classify_capabilities(["task1"], "criteria")

        mock_chain.invoke.assert_called_once_with(_prepare_prompt_values(["task1"], "criteria"))
        assert result.recommendation == "PROCEED"
        assert result.human_actions_needed == ["review"]
        assert result.provider_used == "github-models"

    def test_returns_fallback_when_response_missing_json(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_client = mock.MagicMock()
        mock_chain = mock.MagicMock()
        mock_response = mock.MagicMock()
        mock_response.content = "No JSON here"
        mock_chain.invoke.return_value = mock_response
        self._install_fake_langchain(monkeypatch, mock_chain)

        with mock.patch(
            "scripts.langchain.capability_check._get_llm_client",
            return_value=(mock_client, "github-models"),
        ):
            result = classify_capabilities(["task1"], "criteria")

        assert result.recommendation == "PROCEED"
        assert result.actionable_tasks == ["task1"]
        assert "LLM response missing JSON payload" in result.human_actions_needed
        assert result.provider_used == "github-models"

    def test_returns_fallback_when_response_json_invalid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_client = mock.MagicMock()
        mock_chain = mock.MagicMock()
        mock_response = mock.MagicMock()
        mock_response.content = '{"invalid": }'
        mock_chain.invoke.return_value = mock_response
        self._install_fake_langchain(monkeypatch, mock_chain)

        with mock.patch(
            "scripts.langchain.capability_check._get_llm_client",
            return_value=(mock_client, "github-models"),
        ):
            result = classify_capabilities(["task1"], "criteria")

        assert result.recommendation == "PROCEED"
        assert result.actionable_tasks == ["task1"]
        assert "LLM response JSON parse failed" in result.human_actions_needed
        assert result.provider_used == "github-models"

    def test_fallback_flags_external_dependency(self) -> None:
        with mock.patch("scripts.langchain.capability_check._get_llm_client", return_value=None):
            result = classify_capabilities(["Integrate Stripe payments"], "")
            assert result.recommendation == "BLOCKED"
            assert result.blocked_tasks[0]["task"] == "Integrate Stripe payments"
            assert "external service" in result.blocked_tasks[0]["reason"].lower()

    def test_fallback_flags_admin_requirement(self) -> None:
        with mock.patch("scripts.langchain.capability_check._get_llm_client", return_value=None):
            result = classify_capabilities(["Update GitHub secrets"], "")
            assert result.recommendation == "BLOCKED"
            assert result.blocked_tasks[0]["task"] == "Update GitHub secrets"
            assert "admin" in result.blocked_tasks[0]["reason"].lower()

    def test_fallback_suggests_decomposition(self) -> None:
        with mock.patch("scripts.langchain.capability_check._get_llm_client", return_value=None):
            result = classify_capabilities(["Refactor auth + add tests + update docs"], "")
            assert result.recommendation == "REVIEW_NEEDED"
            assert result.partial_tasks[0]["task"] == "Refactor auth + add tests + update docs"
            assert "split" in result.partial_tasks[0]["limitation"].lower()


# The following tests require langchain_core to be installed
# They test the LLM response handling paths
try:
    from langchain_core.prompts import ChatPromptTemplate  # noqa: F401

    _HAS_LANGCHAIN = True
except ImportError:
    _HAS_LANGCHAIN = False


@pytest.mark.skipif(not _HAS_LANGCHAIN, reason="langchain_core not installed")
class TestClassifyCapabilitiesWithLangchain:
    """Tests that require langchain to be installed."""

    def test_returns_fallback_when_no_json_in_response(self) -> None:
        mock_client = mock.MagicMock()
        mock_response = mock.MagicMock()
        mock_response.content = "No JSON here"

        # Create a mock chain that returns the mock response
        mock_chain = mock.MagicMock()
        mock_chain.invoke.return_value = mock_response

        # Mock the template so that template | client returns our mock chain
        mock_template = mock.MagicMock()
        mock_template.__or__ = mock.MagicMock(return_value=mock_chain)

        with (
            mock.patch(
                "scripts.langchain.capability_check._get_llm_client",
                return_value=(mock_client, "github-models"),
            ),
            mock.patch("langchain_core.prompts.ChatPromptTemplate") as mock_cpt,
        ):
            mock_cpt.from_template.return_value = mock_template

            result = classify_capabilities(["task1"], "criteria")
            assert result.recommendation == "PROCEED"
            assert result.actionable_tasks == ["task1"]
            assert "LLM response missing JSON payload" in result.human_actions_needed

    def test_returns_fallback_when_json_parse_fails(self) -> None:
        mock_client = mock.MagicMock()
        mock_response = mock.MagicMock()
        mock_response.content = '{"invalid": }'

        mock_chain = mock.MagicMock()
        mock_chain.invoke.return_value = mock_response

        mock_template = mock.MagicMock()
        mock_template.__or__ = mock.MagicMock(return_value=mock_chain)

        with (
            mock.patch(
                "scripts.langchain.capability_check._get_llm_client",
                return_value=(mock_client, "github-models"),
            ),
            mock.patch("langchain_core.prompts.ChatPromptTemplate") as mock_cpt,
        ):
            mock_cpt.from_template.return_value = mock_template

            result = classify_capabilities(["task1"], "criteria")
            assert result.recommendation == "PROCEED"
            assert result.actionable_tasks == ["task1"]
            assert "LLM response JSON parse failed" in result.human_actions_needed

    def test_normalizes_valid_llm_response(self) -> None:
        mock_client = mock.MagicMock()
        mock_response = mock.MagicMock()
        mock_response.content = json.dumps(
            {
                "actionable_tasks": ["task1"],
                "partial_tasks": [],
                "blocked_tasks": [],
                "recommendation": "PROCEED",
                "human_actions_needed": [],
            }
        )

        mock_chain = mock.MagicMock()
        mock_chain.invoke.return_value = mock_response

        mock_template = mock.MagicMock()
        mock_template.__or__ = mock.MagicMock(return_value=mock_chain)

        with (
            mock.patch(
                "scripts.langchain.capability_check._get_llm_client",
                return_value=(mock_client, "github-models"),
            ),
            mock.patch("langchain_core.prompts.ChatPromptTemplate") as mock_cpt,
        ):
            mock_cpt.from_template.return_value = mock_template

            result = classify_capabilities(["task1"], "criteria")
            assert result.actionable_tasks == ["task1"]
            assert result.recommendation == "PROCEED"
            assert result.provider_used == "github-models"


class TestMain:
    """Tests for the main CLI function."""

    def test_parses_tasks_json(self) -> None:
        with mock.patch(
            "scripts.langchain.capability_check.classify_capabilities"
        ) as mock_classify:
            mock_classify.return_value = CapabilityCheckResult(
                actionable_tasks=["task1"],
                partial_tasks=[],
                blocked_tasks=[],
                recommendation="PROCEED",
                human_actions_needed=[],
                provider_used="github-models",
            )
            with mock.patch(
                "sys.argv", ["prog", "--tasks-json", '["task1"]', "--acceptance", "criteria"]
            ):
                captured = StringIO()
                with mock.patch("sys.stdout", captured):
                    exit_code = main()
                assert exit_code == 0
                mock_classify.assert_called_once_with(["task1"], "criteria")

    def test_invalid_tasks_json_returns_error(self) -> None:
        with mock.patch("sys.argv", ["prog", "--tasks-json", "not valid json"]):
            captured = StringIO()
            with mock.patch("sys.stderr", captured):
                exit_code = main()
            assert exit_code == 2
            assert "Invalid --tasks-json payload" in captured.getvalue()

    def test_outputs_json_result(self) -> None:
        with mock.patch(
            "scripts.langchain.capability_check.classify_capabilities"
        ) as mock_classify:
            mock_classify.return_value = CapabilityCheckResult(
                actionable_tasks=["task1"],
                partial_tasks=[],
                blocked_tasks=[],
                recommendation="PROCEED",
                human_actions_needed=[],
                provider_used="github-models",
            )
            with mock.patch("sys.argv", ["prog", "--tasks-json", '["task1"]']):
                captured = StringIO()
                with mock.patch("sys.stdout", captured):
                    main()
                output = json.loads(captured.getvalue())
                assert output["actionable_tasks"] == ["task1"]
                assert output["recommendation"] == "PROCEED"

    def test_reads_tasks_and_acceptance_files(self, tmp_path: Any) -> None:
        tasks_file = tmp_path / "tasks.md"
        acceptance_file = tmp_path / "acceptance.md"
        tasks_file.write_text("- task one\n- [ ] task two\n", encoding="utf-8")
        acceptance_file.write_text("criteria here", encoding="utf-8")
        with mock.patch(
            "scripts.langchain.capability_check.classify_capabilities"
        ) as mock_classify:
            mock_classify.return_value = CapabilityCheckResult(
                actionable_tasks=[],
                partial_tasks=[],
                blocked_tasks=[],
                recommendation="REVIEW_NEEDED",
                human_actions_needed=[],
                provider_used=None,
            )
            with mock.patch(
                "sys.argv",
                [
                    "prog",
                    "--tasks-file",
                    str(tasks_file),
                    "--acceptance-file",
                    str(acceptance_file),
                ],
            ):
                exit_code = main()
            assert exit_code == 0
            mock_classify.assert_called_once_with(["task one", "task two"], "criteria here")

    def test_tasks_file_used_when_tasks_json_not_list(self, tmp_path: Any) -> None:
        tasks_file = tmp_path / "tasks.md"
        tasks_file.write_text("- task from file\n", encoding="utf-8")
        with mock.patch(
            "scripts.langchain.capability_check.classify_capabilities"
        ) as mock_classify:
            mock_classify.return_value = CapabilityCheckResult(
                actionable_tasks=[],
                partial_tasks=[],
                blocked_tasks=[],
                recommendation="REVIEW_NEEDED",
                human_actions_needed=[],
                provider_used=None,
            )
            with mock.patch(
                "sys.argv",
                [
                    "prog",
                    "--tasks-json",
                    "{}",
                    "--tasks-file",
                    str(tasks_file),
                    "--acceptance",
                    "criteria",
                ],
            ):
                exit_code = main()
            assert exit_code == 0
            mock_classify.assert_called_once_with(["task from file"], "criteria")


class TestPromptContent:
    """Tests for prompt template content."""

    def test_prompt_includes_known_limitations(self) -> None:
        assert "Cannot modify protected workflow files" in AGENT_CAPABILITY_CHECK_PROMPT
        assert "Cannot change repository settings" in AGENT_CAPABILITY_CHECK_PROMPT
        assert "Cannot retry CI/CD pipelines" in AGENT_CAPABILITY_CHECK_PROMPT

    def test_prompt_includes_classification_options(self) -> None:
        assert "ACTIONABLE" in AGENT_CAPABILITY_CHECK_PROMPT
        assert "PARTIAL" in AGENT_CAPABILITY_CHECK_PROMPT
        assert "BLOCKED" in AGENT_CAPABILITY_CHECK_PROMPT

    def test_prompt_includes_output_format(self) -> None:
        assert "actionable_tasks" in AGENT_CAPABILITY_CHECK_PROMPT
        assert "partial_tasks" in AGENT_CAPABILITY_CHECK_PROMPT
        assert "blocked_tasks" in AGENT_CAPABILITY_CHECK_PROMPT
        assert "recommendation" in AGENT_CAPABILITY_CHECK_PROMPT


class TestIsMultiActionTask:
    """Tests for _is_multi_action_task function."""

    def test_spaced_slashes_detected_as_multi_action(self) -> None:
        """Spaced slashes (alternatives) should be detected as multi-action."""
        from scripts.langchain.capability_check import _is_multi_action_task

        assert _is_multi_action_task("Option A / Option B")
        assert _is_multi_action_task("Run lint / format / typecheck")
        assert _is_multi_action_task("Create issue / PR for changes")

    def test_compound_slashes_not_detected_as_multi_action(self) -> None:
        """Compound words with unspaced slashes should NOT be flagged."""
        from scripts.langchain.capability_check import _is_multi_action_task

        # Compound words - NOT multi-action just due to slash
        assert not _is_multi_action_task("Color-coded additions/removals")
        assert not _is_multi_action_task("Update src/utils module")
        assert not _is_multi_action_task("Fix path/to/file.py")
        assert not _is_multi_action_task("Handle read/write operations")

    def test_other_separators_detected(self) -> None:
        """Other separators should still be detected."""
        from scripts.langchain.capability_check import _is_multi_action_task

        assert _is_multi_action_task("Do this and do that")
        assert _is_multi_action_task("Task A, Task B")
        assert _is_multi_action_task("First + Second")
        assert _is_multi_action_task("Step 1; Step 2")
        assert _is_multi_action_task("Do X then Y")
