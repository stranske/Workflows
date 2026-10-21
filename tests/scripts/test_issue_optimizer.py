from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path
from unittest import mock

import pytest
from scripts.langchain import issue_optimizer


def _install_fake_langchain(monkeypatch: pytest.MonkeyPatch, mock_chain: mock.MagicMock) -> None:
    mock_template = mock.MagicMock()
    mock_template.__or__ = mock.MagicMock(return_value=mock_chain)

    class FakeChatPromptTemplate:
        @staticmethod
        def from_template(_: str):
            return mock_template

    fake_prompts = types.SimpleNamespace(ChatPromptTemplate=FakeChatPromptTemplate)
    fake_core = types.SimpleNamespace(prompts=fake_prompts)
    monkeypatch.setitem(sys.modules, "langchain_core", fake_core)
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", fake_prompts)


def test_extract_suggestions_json_from_comment() -> None:
    result = issue_optimizer.IssueOptimizationResult(
        task_splitting=[],
        blocked_tasks=[
            {
                "task": "Update workflow",
                "reason": "Protected",
                "suggested_action": "Ask human",
            }
        ],
        objective_criteria=[],
        missing_sections=[],
        formatting_issues=[],
        overall_notes="",
        provider_used=None,
    )
    comment = issue_optimizer.format_suggestions_comment(result)
    payload = issue_optimizer._extract_suggestions_json(comment)
    assert payload is not None
    assert payload["blocked_tasks"][0]["task"] == "Update workflow"
    assert "suggestions-json:" in comment


def test_format_suggestions_comment_includes_key_sections() -> None:
    result = issue_optimizer.IssueOptimizationResult(
        task_splitting=[
            {
                "task": "Do two things in one step",
                "reason": "Task combines multiple actions",
                "split_suggestions": ["Split into smaller tasks"],
            }
        ],
        blocked_tasks=[
            {
                "task": "Edit .github/workflows/foo.yml",
                "reason": "Protected",
                "suggested_action": "Ask a human",
            }
        ],
        objective_criteria=[
            {
                "criterion": "Make output nice",
                "issue": "Subjective wording",
                "suggestion": "Specify concrete checks",
            }
        ],
        missing_sections=["Scope"],
        formatting_issues=["Tasks section uses bullets without checkboxes"],
        overall_notes="Review the missing sections.",
        provider_used=None,
    )
    comment = issue_optimizer.format_suggestions_comment(result)
    assert "### Task splitting" in comment
    assert "### Blocked tasks" in comment
    assert "### Objective acceptance criteria" in comment
    assert "<!-- suggestions-json:" in comment


def test_apply_suggestions_fallback_adds_deferred_tasks() -> None:
    issue_body = "Just a note without sections."
    suggestions = {
        "blocked_tasks": [
            {
                "task": "Update workflow",
                "reason": "Protected",
                "suggested_action": "Ask human",
            }
        ]
    }
    result = issue_optimizer.apply_suggestions(issue_body, suggestions, use_llm=False)
    formatted = result["formatted_body"]
    assert "## Deferred Tasks (Requires Human)" in formatted
    assert "- [ ] Update workflow (Protected | Ask human)" in formatted


def test_apply_suggestions_fallback_inserts_decomposed_tasks() -> None:
    issue_body = "## Tasks\n- [ ] Update docs and add tests\n"
    suggestions = {
        "task_splitting": [
            {
                "task": "Update docs and add tests",
                "split_suggestions": [
                    "Update docs (verify: docs updated)",
                    "Add tests (verify: tests pass)",
                ],
            }
        ]
    }
    result = issue_optimizer.apply_suggestions(issue_body, suggestions, use_llm=False)
    formatted = result["formatted_body"]
    assert "- [ ] Update docs and add tests" in formatted
    assert "  - [ ] Update docs (verify: docs updated)" in formatted
    assert "  - [ ] Add tests (verify: tests pass)" in formatted


def test_apply_suggestions_normalizes_subtasks() -> None:
    issue_body = "## Tasks\n- [ ] Update docs\n"
    suggestions = {
        "task_splitting": [
            {
                "task": "Update docs",
                "split_suggestions": [
                    "Add integration tests and update documentation pages",
                    "Depends on backend merge being completed first",
                ],
            }
        ]
    }
    result = issue_optimizer.apply_suggestions(issue_body, suggestions, use_llm=False)
    formatted = result["formatted_body"].lower()
    assert "  - [ ] add integration tests" in formatted
    assert "  - [ ] update documentation pages" in formatted
    assert "document dependency for:" in formatted
    assert "verify:" in formatted


def test_analyze_issue_invokes_llm_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = mock.MagicMock()
    mock_chain = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.content = json.dumps(
        {
            "task_splitting": [],
            "blocked_tasks": [
                {"task": "Update workflow", "reason": "Protected", "suggested_action": "Ask human"}
            ],
            "objective_criteria": [],
            "missing_sections": ["Scope"],
            "formatting_issues": [],
            "overall_notes": "Check formatting",
        }
    )
    mock_chain.invoke.return_value = mock_response

    _install_fake_langchain(monkeypatch, mock_chain)

    with mock.patch(
        "scripts.langchain.issue_optimizer._get_llm_client",
        return_value=(mock_client, "github-models"),
    ):
        result = issue_optimizer.analyze_issue("Issue body", use_llm=True)

    expected_prompt = {
        "issue_body": "Issue body",
        "agent_limitations": "\n".join(f"- {item}" for item in issue_optimizer.AGENT_LIMITATIONS),
    }
    # Verify invoke was called with prompt and config
    assert mock_chain.invoke.call_count == 1
    call_args = mock_chain.invoke.call_args
    assert call_args[0][0] == expected_prompt
    assert "config" in call_args[1]  # LangSmith config passed as kwarg
    assert result.provider_used == "github-models"
    assert result.blocked_tasks[0]["task"] == "Update workflow"


def test_apply_suggestions_llm_path(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = mock.MagicMock()
    mock_chain = mock.MagicMock()
    mock_response = mock.MagicMock()
    mock_response.content = "## Tasks\n- [ ] Do it\n\n## Acceptance Criteria\n- [ ] Done"
    mock_chain.invoke.return_value = mock_response

    _install_fake_langchain(monkeypatch, mock_chain)

    with mock.patch(
        "scripts.langchain.issue_optimizer._get_llm_client",
        return_value=(mock_client, "github-models"),
    ):
        result = issue_optimizer.apply_suggestions(
            "Original body", {"blocked_tasks": []}, use_llm=True
        )

    assert result["used_llm"] is True
    assert result["provider_used"] == "github-models"
    assert "## Tasks" in result["formatted_body"]


def test_extract_suggestions_json_invalid_payload() -> None:
    assert issue_optimizer._extract_suggestions_json("no marker") is None
    assert issue_optimizer._extract_suggestions_json("suggestions-json: {not json") is None


def test_parse_sections_and_checklist_extracts_tasks() -> None:
    body = "\n".join(
        [
            "# Why",
            "Because.",
            "## Tasks",
            "- [ ] First task",
            "- Second task",
            "## Acceptance Criteria",
            "* [x] Must pass tests",
        ]
    )
    sections = issue_optimizer._parse_sections(body)
    tasks = issue_optimizer._parse_checklist(sections["tasks"])
    acceptance = issue_optimizer._parse_checklist(sections["acceptance"])
    assert tasks == ["First task", "Second task"]
    assert acceptance == ["Must pass tests"]


def test_parse_sections_accepts_plain_headings() -> None:
    body = "\n".join(
        [
            "Why",
            "Because.",
            "**Scope**",
            "Only the issue optimizer.",
            "Tasks:",
            "- [ ] First task",
            "Acceptance criteria",
            "- Must pass tests",
            "```",
            "Tasks",
            "- [ ] Not a heading inside code block",
            "```",
        ]
    )
    sections = issue_optimizer._parse_sections(body)
    tasks = issue_optimizer._parse_checklist(sections["tasks"])
    acceptance = issue_optimizer._parse_checklist(sections["acceptance"])
    assert "Only the issue optimizer." in sections["scope"]
    assert tasks == ["First task"]
    assert acceptance == ["Must pass tests"]


def test_parse_checklist_handles_numbered_items() -> None:
    body = "\n".join(
        [
            "## Tasks",
            "1. [ ] First task",
            "2) Second task",
            "## Acceptance Criteria",
            "1. Must pass tests",
        ]
    )
    sections = issue_optimizer._parse_sections(body)
    tasks = issue_optimizer._parse_checklist(sections["tasks"])
    acceptance = issue_optimizer._parse_checklist(sections["acceptance"])
    assert tasks == ["First task", "Second task"]
    assert acceptance == ["Must pass tests"]


def test_parse_checklist_handles_alpha_items() -> None:
    body = "\n".join(
        [
            "## Tasks",
            "a) [ ] First task",
            "b) Second task",
            "## Acceptance Criteria",
            "A) Must pass tests",
        ]
    )
    sections = issue_optimizer._parse_sections(body)
    tasks = issue_optimizer._parse_checklist(sections["tasks"])
    acceptance = issue_optimizer._parse_checklist(sections["acceptance"])
    assert tasks == ["First task", "Second task"]
    assert acceptance == ["Must pass tests"]


def test_detect_blocked_and_subjective_criteria() -> None:
    blocked = issue_optimizer._detect_blocked_tasks(
        ["Edit .github/workflows/ci.yml", "Raise coverage to 80%"]
    )
    assert blocked[0]["reason"] == "Requires workflow changes, which are protected"
    assert blocked[1]["suggested_action"] == "Convert to adding tests and report achieved coverage"

    criteria = issue_optimizer._detect_objective_criteria(["Make output nice"])
    assert criteria[0]["issue"] == "Subjective wording"


def test_detect_objective_criteria_flags_missing_verification_gate() -> None:
    # No criterion references a test / command / smoke gate -> aggregate flag.
    criteria = issue_optimizer._detect_objective_criteria(
        ["The output is correct", "Registration succeeds"]
    )
    issues = [c["issue"] for c in criteria]
    assert any("references a test" in i for i in issues), issues


def test_detect_objective_criteria_no_flag_when_test_named() -> None:
    # At least one criterion names a pytest path::id -> no aggregate flag.
    criteria = issue_optimizer._detect_objective_criteria(
        ["tests/test_register.py::test_rejects_bad_email passes", "Returns HTTP 400"]
    )
    assert all("references a test" not in c["issue"] for c in criteria)


def test_detect_objective_criteria_no_flag_for_command_or_smoke() -> None:
    for criterion in (
        "gh workflow run selftest-ci.yml shows a non-zero collected count",
        "Smoke POST /api/register returns 400",
        "curl -i /health returns 200",
    ):
        criteria = issue_optimizer._detect_objective_criteria([criterion])
        assert all("references a test" not in c["issue"] for c in criteria), criterion


def test_detect_objective_criteria_subjective_and_missing_gate_both() -> None:
    # A subjective criterion that also lacks any verification reference yields
    # BOTH the per-criterion subjective flag and the aggregate gate flag, with
    # the subjective entry preserved first (back-compat).
    criteria = issue_optimizer._detect_objective_criteria(["Make output nice"])
    issues = [c["issue"] for c in criteria]
    assert issues[0] == "Subjective wording"
    assert any("references a test" in i for i in issues), issues


def test_detect_objective_criteria_empty_input_no_flag() -> None:
    # No criteria at all -> nothing to assess; do not emit the aggregate flag
    # (a missing acceptance section is handled by missing_sections elsewhere).
    assert issue_optimizer._detect_objective_criteria([]) == []


def test_fallback_analysis_flags_missing_verification_gate() -> None:
    # End-to-end through the fallback path: an acceptance block with no test
    # reference surfaces the aggregate objective-criteria flag.
    issue_body = (
        "## Tasks\n- [ ] Do the thing\n\n"
        "## Acceptance Criteria\n- [ ] It works correctly\n- [ ] Looks done\n"
    )
    result = issue_optimizer._fallback_analysis(issue_body)
    assert any(
        "references a test" in c.get("issue", "") for c in result.objective_criteria
    ), result.objective_criteria


def test_fallback_analysis_detects_missing_sections() -> None:
    issue_body = "## Tasks\nNot a bullet\n"
    result = issue_optimizer._fallback_analysis(issue_body)
    assert "Acceptance Criteria" in result.missing_sections
    assert "Non-Goals" in result.missing_sections
    assert "Non-bulleted content found in checklist section" in result.formatting_issues


def test_detect_task_splitting_uses_decomposer(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_decompose(task: str, *, use_llm: bool) -> dict[str, list[str]]:
        assert use_llm is False
        return {"sub_tasks": ["Split A", "Split B"]}

    monkeypatch.setattr(
        "scripts.langchain.task_decomposer.decompose_task",
        fake_decompose,
    )
    tasks = ["Update docs and tests in one go"]
    result = issue_optimizer._detect_task_splitting(tasks, use_llm=False)
    assert result[0]["split_suggestions"] == ["Split A", "Split B"]


def test_detect_task_splitting_flags_plus_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_decompose(task: str, *, use_llm: bool) -> dict[str, list[str]]:
        assert task == "Refactor auth + add tests + update docs"
        return {"sub_tasks": ["Refactor auth", "Add tests", "Update docs"]}

    monkeypatch.setattr(
        "scripts.langchain.task_decomposer.decompose_task",
        fake_decompose,
    )
    tasks = ["Refactor auth + add tests + update docs"]
    result = issue_optimizer._detect_task_splitting(tasks, use_llm=False)
    assert result[0]["split_suggestions"] == ["Refactor auth", "Add tests", "Update docs"]


def test_ensure_task_decomposition_fills_missing_suggestions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_decompose(task: str, *, use_llm: bool) -> dict[str, list[str]]:
        assert task == "Large task"
        return {"sub_tasks": ["One", "Two"]}

    monkeypatch.setattr(
        "scripts.langchain.task_decomposer.decompose_task",
        fake_decompose,
    )
    task_splitting = [{"task": "Large task", "split_suggestions": []}]
    updated = issue_optimizer._ensure_task_decomposition(task_splitting, use_llm=True)
    # _ensure_task_decomposition no longer normalizes; that happens
    # in _apply_task_decomposition to avoid double-normalization.
    assert updated[0]["split_suggestions"] == ["One", "Two"]


def test_apply_task_decomposition_skips_when_missing_header() -> None:
    formatted = "## Scope\n- item"
    suggestions = {
        "task_splitting": [
            {"task": "Update docs", "split_suggestions": ["Write docs", "Review docs"]}
        ]
    }
    updated = issue_optimizer._apply_task_decomposition(formatted, suggestions)
    assert updated == formatted


def test_apply_task_decomposition_handles_alpha_items() -> None:
    formatted = "\n".join(
        [
            "## Tasks",
            "a) First task",
            "b) Second task",
            "## Acceptance Criteria",
            "- Works",
        ]
    )
    suggestions = {
        "task_splitting": [
            {
                "task": "First task",
                "split_suggestions": [
                    "Implement the initial setup for deployment",
                    "Configure the test runner to validate results",
                ],
            }
        ]
    }
    updated = issue_optimizer._apply_task_decomposition(formatted, suggestions)
    assert "a) First task" in updated
    # Sub-tasks should appear indented under the parent
    assert "  - [ ]" in updated
    assert "b) Second task" in updated


def test_extract_json_payload_with_wrapped_text() -> None:
    payload = issue_optimizer._extract_json_payload('Result:\n{"ok": true}\nThanks')
    assert payload == '{"ok": true}'


def test_formatted_output_validates_sections() -> None:
    assert issue_optimizer._formatted_output_valid("## Tasks\n- x\n## Acceptance Criteria\n- y")
    assert not issue_optimizer._formatted_output_valid("## Tasks only")


def test_is_large_task_ignores_compound_slashes() -> None:
    """_is_large_task should NOT flag compound words with unspaced slashes."""
    # Compound words should NOT be flagged as large
    assert not issue_optimizer._is_large_task("Color-coded additions/removals")
    assert not issue_optimizer._is_large_task("Update src/utils module")

    # But spaced slashes still indicate alternatives (large task)
    assert issue_optimizer._is_large_task("Option A / Option B")
    assert issue_optimizer._is_large_task("Run lint / format / typecheck")


def test_is_large_task_detects_other_separators() -> None:
    """_is_large_task should still detect other multi-action patterns."""
    assert issue_optimizer._is_large_task("Update docs and add tests")
    assert issue_optimizer._is_large_task("Lint, format, typecheck")
    assert issue_optimizer._is_large_task("Fix bug; write tests")
    assert issue_optimizer._is_large_task("Run A + B")


def _response_with(content: str) -> mock.MagicMock:
    response = mock.MagicMock()
    response.content = content
    return response


def _valid_issue_payload() -> dict[str, object]:
    return {
        "task_splitting": [],
        "blocked_tasks": [],
        "objective_criteria": [],
        "missing_sections": ["Scope"],
        "formatting_issues": [],
        "overall_notes": "All good.",
    }


def test_analyze_issue_guard_blocks_llm(
    monkeypatch: pytest.MonkeyPatch,
    injection_samples: list[dict[str, str]],
) -> None:
    raw = injection_samples[0]["text"]

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("LLM should not be invoked when guard blocks input.")

    monkeypatch.setattr(issue_optimizer, "_get_llm_client", _fail)

    result = issue_optimizer.analyze_issue(raw, use_llm=True)

    assert result.guard_blocked is True
    assert result.guard_reason
    assert result.provider_used is None


def test_apply_suggestions_guard_blocks_llm(
    monkeypatch: pytest.MonkeyPatch,
    injection_samples: list[dict[str, str]],
) -> None:
    raw = injection_samples[0]["text"]

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("LLM should not be invoked when guard blocks input.")

    monkeypatch.setattr(issue_optimizer, "_get_llm_client", _fail)

    result = issue_optimizer.apply_suggestions(raw, {}, use_llm=True)

    assert result["guard_blocked"] is True
    assert result["guard_reason"]
    assert result["used_llm"] is False
    assert result["provider_used"] is None
    assert result["formatted_body"] == raw
    # Verify no redundant 'blocked' key - schema uses only 'guard_blocked'
    assert "blocked" not in result


def test_analyze_issue_valid_output_no_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = mock.MagicMock()
    mock_chain = mock.MagicMock()
    good = json.dumps(_valid_issue_payload())
    mock_chain.invoke.side_effect = [_response_with(good)]

    _install_fake_langchain(monkeypatch, mock_chain)

    with mock.patch(
        "scripts.langchain.issue_optimizer._get_llm_client",
        return_value=(mock_client, "github-models"),
    ):
        result = issue_optimizer.analyze_issue("Issue body", use_llm=True)

    assert result.provider_used == "github-models"
    assert result.missing_sections == ["Scope"]
    assert mock_chain.invoke.call_count == 1
    assert mock_client.invoke.call_count == 0


def test_analyze_issue_repairs_preamble_output(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = mock.MagicMock()
    mock_chain = mock.MagicMock()
    bad = "Here you go:\n" + json.dumps(_valid_issue_payload())
    good = json.dumps(_valid_issue_payload())
    mock_chain.invoke.side_effect = [_response_with(bad)]
    mock_client.invoke.side_effect = [_response_with(good)]

    _install_fake_langchain(monkeypatch, mock_chain)

    with mock.patch(
        "scripts.langchain.issue_optimizer._get_llm_client",
        return_value=(mock_client, "github-models"),
    ):
        result = issue_optimizer.analyze_issue("Issue body", use_llm=True)

    assert result.provider_used == "github-models"
    assert result.missing_sections == ["Scope"]
    assert mock_chain.invoke.call_count == 1
    assert mock_client.invoke.call_count == 1
    repair_prompt = mock_client.invoke.call_args_list[0].args[0]
    assert "Validation errors:" in repair_prompt
    assert "Schema:" in repair_prompt
    assert "Original response:" in repair_prompt


def test_analyze_issue_repairs_fenced_json(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = mock.MagicMock()
    mock_chain = mock.MagicMock()
    bad = "```json\n" + json.dumps(_valid_issue_payload()) + "\n```"
    good = json.dumps(_valid_issue_payload())
    mock_chain.invoke.side_effect = [_response_with(bad)]
    mock_client.invoke.side_effect = [_response_with(good)]

    _install_fake_langchain(monkeypatch, mock_chain)

    with mock.patch(
        "scripts.langchain.issue_optimizer._get_llm_client",
        return_value=(mock_client, "github-models"),
    ):
        result = issue_optimizer.analyze_issue("Issue body", use_llm=True)

    assert result.provider_used == "github-models"
    assert result.missing_sections == ["Scope"]
    assert mock_chain.invoke.call_count == 1
    assert mock_client.invoke.call_count == 1


def test_analyze_issue_repairs_trailing_commas(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = mock.MagicMock()
    mock_chain = mock.MagicMock()
    bad = '{"task_splitting": [], "blocked_tasks": [], "objective_criteria": [], "missing_sections": ["Scope"], "formatting_issues": [], "overall_notes": "All good.",}'
    good = json.dumps(_valid_issue_payload())
    mock_chain.invoke.side_effect = [_response_with(bad)]
    mock_client.invoke.side_effect = [_response_with(good)]

    _install_fake_langchain(monkeypatch, mock_chain)

    with mock.patch(
        "scripts.langchain.issue_optimizer._get_llm_client",
        return_value=(mock_client, "github-models"),
    ):
        result = issue_optimizer.analyze_issue("Issue body", use_llm=True)

    assert result.provider_used == "github-models"
    assert result.missing_sections == ["Scope"]
    assert mock_chain.invoke.call_count == 1
    assert mock_client.invoke.call_count == 1


def test_analyze_issue_repairs_once_then_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = mock.MagicMock()
    mock_chain = mock.MagicMock()
    bad = "Here you go:\n" + json.dumps(_valid_issue_payload())
    mock_chain.invoke.side_effect = [_response_with(bad)]
    mock_client.invoke.side_effect = [_response_with(bad)]

    _install_fake_langchain(monkeypatch, mock_chain)

    with mock.patch(
        "scripts.langchain.issue_optimizer._get_llm_client",
        return_value=(mock_client, "github-models"),
    ):
        result = issue_optimizer.analyze_issue("Issue body", use_llm=True)

    assert result.provider_used is None
    assert "LLM structured output failed" in (result.overall_notes or "")
    assert mock_chain.invoke.call_count == 1
    assert mock_client.invoke.call_count == 1


def test_analyze_issue_langsmith_trace_propagation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that LangSmith trace ID and URL are propagated to result."""
    mock_client = mock.MagicMock()
    mock_chain = mock.MagicMock()

    # Mock response with trace metadata
    mock_response = mock.MagicMock()
    mock_response.content = json.dumps(
        {
            "blocked_tasks": [
                {
                    "task": "Update workflow",
                    "reason": "Protected file",
                    "suggested_action": "Manual update",
                }
            ],
            "suggested_rewrites": [],
            "missing_sections": [],
            "task_splitting_suggestions": [],
        }
    )
    mock_response.response_metadata = {"run_id": "test-run-id-abc123"}
    mock_chain.invoke.return_value = mock_response

    _install_fake_langchain(monkeypatch, mock_chain)

    with (
        mock.patch(
            "scripts.langchain.issue_optimizer._get_llm_client",
            return_value=(mock_client, "test-provider"),
        ),
        mock.patch.dict("os.environ", {"LANGSMITH_API_KEY": "test-key"}),
    ):
        result = issue_optimizer.analyze_issue("Issue body", use_llm=True)

    # Assert trace fields are populated
    assert hasattr(result, "langsmith_trace_id")
    assert hasattr(result, "langsmith_trace_url")
    assert result.langsmith_trace_id == "test-run-id-abc123"
    assert "test-run-id-abc123" in (result.langsmith_trace_url or "")
    assert result.provider_used == "test-provider"


def test_apply_suggestions_langsmith_trace_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that apply_suggestions includes LangSmith trace fields when available."""
    mock_client = mock.MagicMock()
    mock_chain = mock.MagicMock()

    # Mock response with trace metadata
    mock_response = mock.MagicMock()
    mock_response.content = "## Tasks\n- [ ] Do it\n\n## Acceptance Criteria\n- [ ] Done"
    mock_response.response_metadata = {"run_id": "apply-trace-xyz789"}
    mock_chain.invoke.return_value = mock_response

    _install_fake_langchain(monkeypatch, mock_chain)

    # Minimal suggestions dict
    suggestions = {
        "task_splitting": [],
        "blocked_tasks": [],
        "objective_criteria": [],
        "overall_notes": "",
    }

    with (
        mock.patch(
            "scripts.langchain.issue_optimizer._get_llm_client",
            return_value=(mock_client, "test-provider"),
        ),
        mock.patch.dict("os.environ", {"LANGSMITH_API_KEY": "test-key"}),
    ):
        result = issue_optimizer.apply_suggestions("Issue body", suggestions, use_llm=True)

    # Assert trace fields are included in returned dict
    assert isinstance(result, dict)
    assert "langsmith_trace_id" in result
    assert "langsmith_trace_url" in result
    assert result["langsmith_trace_id"] == "apply-trace-xyz789"
    assert "apply-trace-xyz789" in result["langsmith_trace_url"]
    assert result["provider_used"] == "test-provider"


def test_context_environment_helpers_accept_only_safe_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed context budget must retain the bounded default."""
    monkeypatch.setenv("ISSUE_PR_CONTEXT_TOKEN_BUDGET", "not-a-number")
    assert issue_optimizer._context_token_budget() == 4000
    monkeypatch.setenv("ISSUE_PR_CONTEXT_TOKEN_BUDGET", "250")
    monkeypatch.setenv("ISSUE_PR_CONTEXT_WORKFLOW", "custom-consumer")
    assert issue_optimizer._context_token_budget() == 250
    assert issue_optimizer._context_workflow("issue_optimizer") == "custom-consumer"


def test_invoke_llm_retries_without_config_for_legacy_chain() -> None:
    """The compatibility retry is required for chains without config support."""
    chain = mock.MagicMock()
    response = object()
    chain.invoke.side_effect = [TypeError("unexpected config"), response]

    actual, trace_id, trace_url = issue_optimizer._invoke_llm_with_trace(
        chain, {"body": "issue"}, operation="analyze_issue"
    )

    assert actual is response
    assert trace_id is None
    assert trace_url is None
    assert chain.invoke.call_args_list[1].args == ({"body": "issue"},)


# ---------------------------------------------------------------------------
# Anti-bloat: decomposition caps, idempotency, no-silent-loss with sentinels
# ---------------------------------------------------------------------------


def _top_level_task_lines(body: str) -> list[str]:
    lines = body.splitlines()
    header_idx = next(i for i, line in enumerate(lines) if line.strip() == "## Tasks")
    end_idx = next(
        (
            i
            for i in range(header_idx + 1, len(lines))
            if lines[i].startswith("## ") and lines[i].strip() != "## Tasks"
        ),
        len(lines),
    )
    return [
        line
        for line in lines[header_idx + 1 : end_idx]
        if line.strip().startswith(("- [", "* [", "1.", "a)")) and not line.startswith("  ")
    ]


def test_apply_six_task_issue_stays_within_max_tasks_no_triple() -> None:
    """A 6-task issue must not explode into per-task scope/implement/validate triples."""
    from scripts.langchain import task_decomposer

    tasks = [
        "Define common constraints for weight bounds",
        "Implement ConstraintValidator class",
        "Add validation hooks in portfolio construction",
        "Generate suggestions for constraint violations",
        "Add a --validate-only CLI flag",
        "Document the supported constraints",
    ]
    body = (
        "## Tasks\n"
        + "\n".join(f"- [ ] {t}" for t in tasks)
        + "\n\n## Acceptance Criteria\n- [ ] tests pass\n"
    )
    # No split suggestions provided: tasks should pass through unmultiplied.
    result = issue_optimizer.apply_suggestions(body, {}, use_llm=False)
    formatted = result["formatted_body"]

    top = _top_level_task_lines(formatted)
    # Six tasks in, at most six top-level tasks out (well under the cap), no triple.
    assert len(top) == len(tasks)
    assert len(top) <= task_decomposer.MAX_TASKS
    assert "focused slice for" not in formatted.lower()
    # Each original task appears exactly once in the Tasks section (no triple,
    # no near-duplicate). It may also appear in the preserved Original-Issue block.
    for task in tasks:
        assert sum(1 for line in top if task in line) == 1


def test_apply_caps_tasks_at_max_with_elision_sentinel() -> None:
    """Over-cap task lists are trimmed but emit an explicit elided sentinel.

    The elision keeps the no-silent-loss contract: nothing vanishes silently.
    """
    from scripts.langchain import task_decomposer

    over = task_decomposer.MAX_TASKS + 5
    body = (
        "## Tasks\n"
        + "\n".join(f"- [ ] Task number {i} does distinct work item {i}" for i in range(over))
        + "\n\n## Acceptance Criteria\n- [ ] it works\n"
    )
    formatted = issue_optimizer.apply_suggestions(body, {}, use_llm=False)["formatted_body"]
    top = _top_level_task_lines(formatted)

    # MAX_TASKS real items + 1 sentinel line accounting for the remainder.
    assert len([line for line in top if not task_decomposer.is_elision_sentinel(line)]) == (
        task_decomposer.MAX_TASKS
    )
    sentinels = [line for line in top if task_decomposer.is_elision_sentinel(line)]
    assert len(sentinels) == 1
    assert "elided" in sentinels[0]


def test_apply_three_cycles_single_original_issue_block() -> None:
    """Three apply cycles must leave exactly one Original-Issue <details> block."""
    suggestions = {
        "task_splitting": [
            {
                "task": "Update docs and add tests",
                "split_suggestions": [
                    "Update the documentation pages thoroughly",
                    "Add unit tests for the new code path",
                ],
            }
        ]
    }
    body = "## Tasks\n- [ ] Update docs and add tests\n\n## Acceptance Criteria\n- [ ] tests pass\n"
    c1 = issue_optimizer.apply_suggestions(body, suggestions, use_llm=False)["formatted_body"]
    c2 = issue_optimizer.apply_suggestions(c1, suggestions, use_llm=False)["formatted_body"]
    c3 = issue_optimizer.apply_suggestions(c2, suggestions, use_llm=False)["formatted_body"]

    assert c1.count("<summary>Original Issue</summary>") == 1
    assert c3.count("<summary>Original Issue</summary>") == 1
    # And the body stabilizes rather than growing each cycle.
    assert c3 == c2


def test_apply_is_byte_stable_across_reruns() -> None:
    """Re-applying the same suggestions must not keep growing the body."""
    suggestions = {
        "task_splitting": [
            {
                "task": "Update docs and add tests",
                "split_suggestions": [
                    "Update the documentation pages thoroughly",
                    "Add unit tests for the new code path",
                ],
            }
        ]
    }
    body = "## Tasks\n- [ ] Update docs and add tests\n\n## Acceptance Criteria\n- [ ] tests pass\n"
    a1 = issue_optimizer.apply_suggestions(body, suggestions, use_llm=False)["formatted_body"]
    a2 = issue_optimizer.apply_suggestions(a1, suggestions, use_llm=False)["formatted_body"]
    a3 = issue_optimizer.apply_suggestions(a2, suggestions, use_llm=False)["formatted_body"]
    assert a2 == a3
    assert len(a3) <= len(a2)


def test_deduplicate_task_lines_collapses_near_duplicates() -> None:
    """Near-duplicate tasks (paraphrases) collapse, not just exact matches."""
    formatted = "\n".join(
        [
            "## Tasks",
            "- [ ] Add tests for the parser module",
            "- [ ] Add unit tests for the parser module",
            "- [ ] Document the public API surface",
            "## Acceptance Criteria",
            "- [ ] it works",
        ]
    )
    deduped = issue_optimizer._deduplicate_task_lines(formatted)
    top = _top_level_task_lines(deduped)
    # The two near-identical "Add ... tests for the parser module" collapse to one.
    assert sum(1 for line in top if "parser module" in line) == 1
    assert any("public API surface" in line for line in top)


def test_apply_resets_oversized_body_to_embedded_original() -> None:
    """An oversized ballooned body is reset to its embedded Original Issue."""
    original = "Why: real intent\n\nTasks:\n- do the real thing\n\nAcceptance:\n- it works"
    n_padding = 3000
    bloated = (
        "## Tasks\n"
        + "\n".join(f"- [ ] padding task {i}" for i in range(n_padding))
        + "\n\n## Acceptance Criteria\n- [ ] x\n\n<details>\n<summary>Original Issue</summary>\n\n"
        + f"```text\n{original}\n```\n</details>"
    )
    assert len(bloated) > issue_optimizer.MAX_ISSUE_BODY_SIZE
    formatted = issue_optimizer.apply_suggestions(bloated, {}, use_llm=False)["formatted_body"]
    # The reset re-formats the small original, so the result is far smaller and
    # carries the real task, not the thousands of padding tasks.
    assert len(formatted) < len(bloated)
    assert "do the real thing" in formatted
    assert f"padding task {n_padding - 1}" not in formatted


def test_apply_no_silent_loss_audit_passes_with_caps() -> None:
    """Capping must never trip the no-silent-loss audit; sentinels keep it balanced.

    Re-formatting a capped body routes its Tasks (including the elision sentinel)
    through task_validator.validate_tasks / merge_with_audit. That audit raises on
    unaccounted loss; this asserts it does not.
    """
    from scripts.langchain import issue_formatter, task_decomposer

    over = task_decomposer.MAX_TASKS + 8
    body = (
        "## Tasks\n"
        + "\n".join(f"- [ ] Distinct work item number {i} to complete" for i in range(over))
        + "\n\n## Acceptance Criteria\n- [ ] it works\n"
    )
    capped = issue_optimizer.apply_suggestions(body, {}, use_llm=False)["formatted_body"]

    # Sentinel must be present (the elided remainder is accounted for, not dropped).
    assert any(task_decomposer.is_elision_sentinel(line) for line in _top_level_task_lines(capped))

    # Re-formatting the capped body must not raise the audit ValueError.
    reformatted = issue_formatter.format_issue_body(capped, use_llm=False)
    assert reformatted["formatted_body"] is not None
    # The sentinel survives the validator round-trip.
    assert "elided" in reformatted["formatted_body"]


def test_optimizer_helpers_preserve_usable_data_and_cap_overflow() -> None:
    """Malformed suggestions are ignored while real checkbox overflow remains explicit."""
    result = issue_optimizer.IssueOptimizationResult(
        task_splitting=[{"task": "Split the import work", "reason": "two actions"}, "bad"],
        blocked_tasks=[{"task": "", "reason": "ignored"}, "bad"],
        objective_criteria=[{"criterion": "", "issue": "ignored"}, "bad"],
        missing_sections=[],
        formatting_issues=[],
        overall_notes="",
        provider_used="provider",
        guard_blocked=True,
        guard_reason="unsafe input",
        langsmith_trace_id="trace-1",
        langsmith_trace_url="https://example.invalid/trace-1",
    )
    payload = result.to_dict()

    assert payload["guard_reason"] == "unsafe input"
    assert payload["langsmith_trace_id"] == "trace-1"
    assert issue_optimizer._format_task_splitting(result.task_splitting) == [
        "Split the import work (two actions)."
    ]
    assert issue_optimizer._format_blocked_tasks(result.blocked_tasks) == []
    assert issue_optimizer._format_objective_criteria(result.objective_criteria) == []
    assert issue_optimizer._coerce_split_suggestions(
        {"split_suggestions": ["Tiny", "Write a focused regression test for parsing"]}
    ) == ["Write a focused regression test for parsing"]

    from scripts.langchain import task_decomposer

    source = "\n".join(
        [
            "## Tasks",
            "- [ ] First task",
            "  - [ ] Retained detail",
            "- [ ] Second task",
            "  - [ ] Nested detail",
            "## Acceptance Criteria",
            "- [ ] Check one",
        ]
    )
    capped = issue_optimizer._cap_section_items(source, "## Tasks", 1, kind="tasks")
    assert "- [ ] First task" in capped
    assert "- [ ] Second task" not in capped
    assert "  - [ ] Retained detail" in capped
    assert "  - [ ] Nested detail" not in capped
    assert task_decomposer.elision_sentinel(1, kind="tasks") in capped
    assert issue_optimizer._cap_section_items(source, "## Missing", 1, kind="tasks") == source


def test_fallback_paths_keep_structured_issue_when_llm_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both public operations retain useful output when no provider is configured."""
    monkeypatch.setattr(issue_optimizer, "_get_llm_client", lambda **_kwargs: None)
    body = "## Tasks\n- [ ] Update docs and tests\n\n## Acceptance Criteria\n- [ ] pytest tests/scripts\n"

    analyzed = issue_optimizer.analyze_issue(body, use_llm=True)
    applied = issue_optimizer.apply_suggestions(
        body,
        {
            "task_splitting": [None, {"task": "", "split_suggestions": ["ignored"]}],
            "blocked_tasks": [None, {"reason": "missing task"}],
        },
        use_llm=True,
    )

    assert analyzed.provider_used is None
    assert "Fallback analysis used" in (analyzed.overall_notes or "")
    assert applied["used_llm"] is False
    assert "## Tasks" in applied["formatted_body"]
    assert "Deferred Tasks" not in applied["formatted_body"]


def test_provider_token_limit_falls_back_to_formatter_when_openai_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A GitHub Models token-limit failure does not discard an issue body."""
    primary_chain = mock.MagicMock()
    primary_chain.invoke.side_effect = RuntimeError("token limit")
    mock_template = mock.MagicMock()
    mock_template.__or__ = mock.MagicMock(return_value=primary_chain)

    class FakeChatPromptTemplate:
        @staticmethod
        def from_template(_: str):
            return mock_template

    fake_prompts = types.SimpleNamespace(ChatPromptTemplate=FakeChatPromptTemplate)
    monkeypatch.setitem(sys.modules, "langchain_core", types.SimpleNamespace(prompts=fake_prompts))
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", fake_prompts)
    monkeypatch.setattr(
        issue_optimizer,
        "_get_llm_client",
        mock.MagicMock(side_effect=[(mock.MagicMock(), "github-models"), None]),
    )
    monkeypatch.setattr("tools.llm_provider._is_token_limit_error", lambda _error: True)

    result = issue_optimizer.analyze_issue("## Tasks\n- [ ] Add tests", use_llm=True)

    assert result.provider_used is None
    assert "Fallback analysis used" in (result.overall_notes or "")
    assert "retrying with OpenAI API" in capsys.readouterr().err


def test_analyze_issue_recovers_with_openai_after_github_models_token_limit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A successful OpenAI retry is returned instead of the local heuristic fallback."""
    primary_chain = mock.MagicMock()
    primary_chain.invoke.side_effect = RuntimeError("token limit")
    openai_chain = mock.MagicMock()
    openai_chain.invoke.return_value = _response_with(json.dumps(_valid_issue_payload()))
    mock_template = mock.MagicMock()
    mock_template.__or__ = mock.MagicMock(side_effect=[primary_chain, openai_chain])

    class FakeChatPromptTemplate:
        @staticmethod
        def from_template(_: str):
            return mock_template

    fake_prompts = types.SimpleNamespace(ChatPromptTemplate=FakeChatPromptTemplate)
    monkeypatch.setitem(sys.modules, "langchain_core", types.SimpleNamespace(prompts=fake_prompts))
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", fake_prompts)
    monkeypatch.setattr(
        issue_optimizer,
        "_get_llm_client",
        mock.MagicMock(
            side_effect=[
                (mock.MagicMock(), "github-models"),
                (mock.MagicMock(), "openai"),
            ]
        ),
    )
    monkeypatch.setattr("tools.llm_provider._is_token_limit_error", lambda _error: True)

    result = issue_optimizer.analyze_issue("Issue body", use_llm=True)

    assert result.provider_used == "openai"
    assert result.missing_sections == ["Scope"]
    assert "Successfully analyzed with OpenAI API" in capsys.readouterr().err


def test_apply_suggestions_recovers_with_openai_after_github_models_token_limit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Suggestion application retries a token-limited provider without losing a valid body."""
    primary_chain = mock.MagicMock()
    primary_chain.invoke.side_effect = RuntimeError("token limit")
    openai_chain = mock.MagicMock()
    openai_chain.invoke.return_value = _response_with(
        "## Tasks\n- [ ] Preserve original task\n\n## Acceptance Criteria\n- [ ] pytest passes"
    )
    mock_template = mock.MagicMock()
    mock_template.__or__ = mock.MagicMock(side_effect=[primary_chain, openai_chain])

    class FakeChatPromptTemplate:
        @staticmethod
        def from_template(_: str):
            return mock_template

    fake_prompts = types.SimpleNamespace(ChatPromptTemplate=FakeChatPromptTemplate)
    monkeypatch.setitem(sys.modules, "langchain_core", types.SimpleNamespace(prompts=fake_prompts))
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", fake_prompts)
    monkeypatch.setattr(
        issue_optimizer,
        "_get_llm_client",
        mock.MagicMock(
            side_effect=[
                (mock.MagicMock(), "github-models"),
                (mock.MagicMock(), "openai"),
            ]
        ),
    )
    monkeypatch.setattr("tools.llm_provider._is_token_limit_error", lambda _error: True)

    result = issue_optimizer.apply_suggestions("Issue body", {}, use_llm=True)

    assert result["provider_used"] == "openai"
    assert result["used_llm"] is True
    assert "Preserve original task" in result["formatted_body"]
    assert "Successfully applied suggestions with OpenAI API" in capsys.readouterr().err


def test_apply_suggestions_falls_back_when_openai_retry_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failed OpenAI retry leaves the formatter fallback available to the operator."""
    primary_chain = mock.MagicMock()
    primary_chain.invoke.side_effect = RuntimeError("token limit")
    openai_chain = mock.MagicMock()
    openai_chain.invoke.side_effect = RuntimeError("service unavailable")
    mock_template = mock.MagicMock()
    mock_template.__or__ = mock.MagicMock(side_effect=[primary_chain, openai_chain])

    class FakeChatPromptTemplate:
        @staticmethod
        def from_template(_: str):
            return mock_template

    fake_prompts = types.SimpleNamespace(ChatPromptTemplate=FakeChatPromptTemplate)
    monkeypatch.setitem(sys.modules, "langchain_core", types.SimpleNamespace(prompts=fake_prompts))
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", fake_prompts)
    monkeypatch.setattr(
        issue_optimizer,
        "_get_llm_client",
        mock.MagicMock(
            side_effect=[
                (mock.MagicMock(), "github-models"),
                (mock.MagicMock(), "openai"),
            ]
        ),
    )
    monkeypatch.setattr("tools.llm_provider._is_token_limit_error", lambda _error: True)

    result = issue_optimizer.apply_suggestions("## Tasks\n- [ ] Preserve task", {}, use_llm=True)

    assert result["provider_used"] is None
    assert result["used_llm"] is False
    assert "OpenAI API also failed" in capsys.readouterr().err


def test_cli_main_emits_plain_text_for_analysis_and_apply(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Human CLI output follows the same public paths as JSON output."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["issue_optimizer.py", "--input-text", "## Tasks\n- [ ] Test", "--no-llm"],
    )
    issue_optimizer.main()
    assert "Fallback analysis used" in capsys.readouterr().out

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "issue_optimizer.py",
            "--input-text",
            "## Tasks\n- [ ] Test\n\n## Acceptance Criteria\n- [ ] pytest",
            "--apply-suggestions",
            "--suggestions-json",
            "{}",
            "--no-llm",
        ],
    )
    issue_optimizer.main()
    assert "## Tasks" in capsys.readouterr().out


def test_cli_loaders_and_main_handle_all_supported_suggestion_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI loading accepts supported sources and exits visibly on invalid apply input."""
    path = tmp_path / "issue.md"
    path.write_text("from file", encoding="utf-8")
    suggestions = tmp_path / "suggestions.json"
    suggestions.write_text('{"blocked_tasks": []}', encoding="utf-8")
    comment = tmp_path / "comment.md"
    comment.write_text('<!-- suggestions-json: {"blocked_tasks": []} -->', encoding="utf-8")

    assert (
        issue_optimizer._load_input(argparse.Namespace(input_file=str(path), input_text=None))
        == "from file"
    )
    assert (
        issue_optimizer._load_input(argparse.Namespace(input_file=None, input_text="inline"))
        == "inline"
    )
    assert issue_optimizer._load_suggestions(
        argparse.Namespace(
            suggestions_json='{"blocked_tasks": []}',
            suggestions_file=None,
            suggestions_comment_file=None,
            suggestions_comment_text=None,
        )
    ) == {"blocked_tasks": []}
    assert issue_optimizer._load_suggestions(
        argparse.Namespace(
            suggestions_json=None,
            suggestions_file=str(suggestions),
            suggestions_comment_file=None,
            suggestions_comment_text=None,
        )
    ) == {"blocked_tasks": []}
    assert issue_optimizer._load_suggestions(
        argparse.Namespace(
            suggestions_json=None,
            suggestions_file=None,
            suggestions_comment_file=str(comment),
            suggestions_comment_text=None,
        )
    ) == {"blocked_tasks": []}

    monkeypatch.setattr(
        sys,
        "argv",
        ["issue_optimizer.py", "--input-text", "raw", "--apply-suggestions", "--no-llm"],
    )
    with pytest.raises(SystemExit, match="1"):
        issue_optimizer.main()
    assert "Failed to load suggestions JSON." in capsys.readouterr().err


def test_cli_main_emits_json_for_analysis_and_apply(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command-line entry point exposes both machine-readable public operations."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["issue_optimizer.py", "--input-text", "## Tasks\n- [ ] Test", "--no-llm", "--json"],
    )
    issue_optimizer.main()
    analysis = json.loads(capsys.readouterr().out)
    assert analysis["provider_used"] is None

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "issue_optimizer.py",
            "--input-text",
            "## Tasks\n- [ ] Test\n\n## Acceptance Criteria\n- [ ] pytest",
            "--apply-suggestions",
            "--suggestions-json",
            "{}",
            "--no-llm",
            "--json",
        ],
    )
    issue_optimizer.main()
    applied = json.loads(capsys.readouterr().out)
    assert applied["used_llm"] is False
    assert "## Tasks" in applied["formatted_body"]


def test_structural_helpers_handle_empty_sections_sentinels_and_invalid_entries() -> None:
    """Section manipulation keeps non-task structure and rejects unusable suggestions."""
    from scripts.langchain import task_decomposer

    assert issue_optimizer._deduplicate_task_lines("No task header") == "No task header"
    assert issue_optimizer._section_bounds(["## Tasks", "- [ ] one"], "## Missing") is None
    assert issue_optimizer._section_duplication_ratio("plain text") == 0.0
    assert issue_optimizer._section_duplication_ratio("## Tasks\n- one\n## tasks\n- two") == 1.0
    assert issue_optimizer._is_near_duplicate(frozenset(), [frozenset({"task"})]) is False
    assert issue_optimizer._is_near_duplicate(frozenset({"task"}), [frozenset()]) is False
    assert issue_optimizer._is_near_duplicate(
        frozenset({"add", "tests", "parser"}), [frozenset({"add", "tests", "parser"})]
    )

    sentinel = task_decomposer.elision_sentinel(2, kind="sub-tasks")
    body = "\n".join(
        [
            "## Tasks",
            "- [ ] Parent task",
            "## Acceptance Criteria",
            "- [ ] pytest",
        ]
    )
    applied = issue_optimizer._apply_task_decomposition(
        body,
        {
            "task_splitting": [
                None,
                {"task": "", "split_suggestions": ["ignored"]},
                {"task": "Parent task", "split_suggestions": [sentinel, "Tiny"]},
            ]
        },
    )
    assert sentinel in applied
    assert "  - [ ] Tiny" not in applied
    assert issue_optimizer._apply_task_decomposition(None, {}) == ""
    assert issue_optimizer._apply_task_decomposition(body, {"task_splitting": []}) == body
    assert issue_optimizer._append_deferred_tasks(body, {"blocked_tasks": "invalid"}) == body
    deferred = issue_optimizer._append_deferred_tasks(
        body, {"blocked_tasks": [{"task": "Ask human"}]}
    )
    updated = issue_optimizer._append_deferred_tasks(
        deferred + "\n\n## Notes\nPreserve this section",
        {"blocked_tasks": [{"task": "Different task"}]},
    )
    assert updated.count("## Deferred Tasks (Requires Human)") == 1
    assert "- [ ] Ask human" in updated
    assert "- [ ] Different task" in updated
    assert updated.index("Different task") < updated.index("## Notes")
    assert updated.endswith("Preserve this section")
    assert (
        issue_optimizer._append_deferred_tasks(
            updated, {"blocked_tasks": [{"task": "Different task"}]}
        )
        == updated
    )


def test_loaders_and_llm_response_errors_are_explicit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Invalid file/JSON input and failed structured output stay non-authorizing."""
    missing = tmp_path / "missing.json"
    malformed = tmp_path / "malformed.json"
    malformed.write_text("not json", encoding="utf-8")
    common = {
        "suggestions_json": None,
        "suggestions_file": None,
        "suggestions_comment_file": None,
        "suggestions_comment_text": None,
    }
    assert (
        issue_optimizer._load_suggestions(
            argparse.Namespace(**{**common, "suggestions_json": "[]"})
        )
        is None
    )
    assert (
        issue_optimizer._load_suggestions(
            argparse.Namespace(**{**common, "suggestions_file": str(missing)})
        )
        is None
    )
    assert (
        issue_optimizer._load_suggestions(
            argparse.Namespace(**{**common, "suggestions_file": str(malformed)})
        )
        is None
    )
    assert (
        issue_optimizer._load_suggestions(
            argparse.Namespace(**{**common, "suggestions_comment_file": str(missing)})
        )
        is None
    )
    assert (
        issue_optimizer._load_suggestions(
            argparse.Namespace(**{**common, "suggestions_comment_text": "not a marker"})
        )
        is None
    )
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(read=lambda: "from stdin"))
    assert (
        issue_optimizer._load_input(argparse.Namespace(input_file=None, input_text=None))
        == "from stdin"
    )

    for stage, expected in (
        ("repair_unavailable", "could not be repaired"),
        ("repair_validation", "repair failed validation"),
        ("validation", "output failed validation"),
    ):
        parsed = types.SimpleNamespace(payload=None, error_stage=stage, error_detail="bad schema")
        monkeypatch.setattr(
            issue_optimizer,
            "parse_structured_output",
            lambda *_args, parsed=parsed, **_kwargs: parsed,
        )
        result, error = issue_optimizer._process_llm_response(object(), "provider", use_llm=False)
        assert result is None
        assert expected in (error or "")


def test_local_prompt_fallbacks_work_without_optional_prompt_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Local execution uses built-in prompts and metadata when optional services are absent."""
    monkeypatch.setattr(issue_optimizer, "PROMPT_PATH", tmp_path / "missing-analyze.md")
    monkeypatch.setattr(issue_optimizer, "APPLY_PROMPT_PATH", tmp_path / "missing-apply.md")
    monkeypatch.setitem(sys.modules, "tools.llm_provider", None)
    monkeypatch.setenv("GITHUB_REPOSITORY", "stranske/Workflows")
    monkeypatch.setenv("RUN_ID", "run-7")
    monkeypatch.setenv("ISSUE_NUMBER", "42")

    assert issue_optimizer._load_prompt() == issue_optimizer.ANALYZE_ISSUE_PROMPT
    assert issue_optimizer._load_apply_prompt() == issue_optimizer.APPLY_SUGGESTIONS_PROMPT
    config = issue_optimizer._build_llm_config(operation="analyze_issue")
    assert config["metadata"]["issue_or_pr_number"] == "42"
    assert "repo:stranske/Workflows" in config["tags"]


def test_parser_and_invoker_handle_code_blocks_and_legacy_chain_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The parser ignores checklist-looking code and invocation retries legacy chains."""
    body = "\n".join(
        [
            "## Tasks",
            "```text",
            "- [ ] Not a task",
            "```",
            "Task prose",
            "## Acceptance Criteria",
            "- [ ] Real check",
        ]
    )
    sections = issue_optimizer._parse_sections(body)
    assert issue_optimizer._parse_checklist(sections["tasks"]) == []
    assert issue_optimizer._detect_formatting_issues(sections["tasks"]) == [
        "Non-bulleted content found in checklist section"
    ]
    assert issue_optimizer._strip_checkbox("plain text") == "plain text"
    assert issue_optimizer._extract_json_payload("prefix only") is None
    assert issue_optimizer._formatted_output_valid("") is False

    chain = mock.MagicMock()
    response = object()
    chain.invoke.side_effect = [TypeError("no config"), response]
    monkeypatch.setattr(issue_optimizer, "_build_llm_config", lambda **_kwargs: {"metadata": {}})
    actual, trace_id, trace_url = issue_optimizer._invoke_llm_with_trace(
        chain, {"body": "x"}, operation="test"
    )
    assert actual is response
    assert trace_id is None
    assert trace_url is None
    assert chain.invoke.call_count == 2


def test_optimizer_helpers_reject_empty_or_unactionable_optional_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert issue_optimizer._extract_json_payload("{}") == "{}"
    assert issue_optimizer._extract_suggestions_json("") is None
    assert issue_optimizer._coerce_split_suggestions({"split_suggestions": "not-a-list"}) == []
    assert issue_optimizer._coerce_split_suggestions({"split_suggestions": ["", "too short"]}) == []
    assert issue_optimizer._is_large_task(
        "one two three four five six seven eight nine ten eleven twelve thirteen fourteen"
    )
    assert issue_optimizer._is_large_task("Add tests and update docs")
    assert (
        issue_optimizer._ensure_task_decomposition(["invalid", {"task": ""}], use_llm=False) == []
    )

    chain = mock.MagicMock()
    chain.invoke.return_value = object()
    monkeypatch.setattr(issue_optimizer, "_build_llm_config", lambda **_kwargs: {})
    monkeypatch.setitem(sys.modules, "tools.llm_provider", None)
    response, trace_id, trace_url = issue_optimizer._invoke_llm_with_trace(
        chain, {"body": "x"}, operation="test"
    )
    assert response is chain.invoke.return_value
    assert trace_id is None
    assert trace_url is None


def test_optimizer_edge_paths_cover_json_elision_oversized_and_caps(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts.langchain import task_decomposer

    assert (
        issue_optimizer._extract_suggestions_json("<!-- suggestions-json: {not-json} -->") is None
    )
    assert issue_optimizer._extract_suggestions_json("<!-- suggestions-json: [] -->") is None
    sentinel = task_decomposer.elision_sentinel(1, kind="tasks")
    deduped = issue_optimizer._deduplicate_task_lines(
        "\n".join(
            [
                "## Tasks",
                "- [ ] Keep",
                f"- [ ] {sentinel}",
                "- [ ]   ",
                "## Acceptance Criteria",
                "- [ ] Done",
            ]
        )
    )
    assert sentinel in deduped

    # Oversized bodies with no embedded original return None (no silent truncate).
    monkeypatch.setattr(
        "scripts.langchain.issue_formatter._innermost_original_issue",
        lambda _body: "",
    )
    from scripts.langchain.issue_formatter import MAX_ISSUE_BODY_SIZE

    oversized = "x" * (MAX_ISSUE_BODY_SIZE + 1)
    assert issue_optimizer._reset_oversized_body(oversized, "issue_optimizer") is None

    kept, elided = issue_optimizer._cap_checkbox_lines(
        [
            "- [ ] one",
            "- [ ] two",
            "  - [ ] nested under two",
            "heading",
            "- [ ] three",
        ],
        max_items=1,
        kind="tasks",
    )
    assert elided == 2
    assert "nested under two" not in "\n".join(kept)
    assert "heading" in "\n".join(kept)

    monkeypatch.setattr(
        "scripts.langchain.task_decomposer.decompose_task",
        lambda _task, use_llm=False: {"sub_tasks": []},
    )
    splits = issue_optimizer._detect_task_splitting(
        ["Add tests and update documentation thoroughly"], use_llm=False
    )
    assert splits and splits[0]["split_suggestions"] == ["Split into smaller, single-action tasks"]

    result = issue_optimizer.analyze_issue("", use_llm=False)
    assert result.provider_used is None

    body_without_tasks = "## Scope\nDo work\n\n## Acceptance Criteria\n- [ ] Done"
    assert (
        issue_optimizer._apply_task_decomposition(
            body_without_tasks,
            {
                "task_splitting": [
                    {
                        "task": "Do work",
                        "split_suggestions": ["Write tests for the parser path"],
                    }
                ]
            },
        )
        == body_without_tasks
    )


def test_analyze_and_apply_cover_import_error_and_non_token_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        issue_optimizer,
        "_get_llm_client",
        mock.MagicMock(return_value=(mock.MagicMock(), "openai")),
    )
    monkeypatch.setitem(sys.modules, "langchain_core", None)
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", None)
    # ImportError path clears client_info and falls back.
    result = issue_optimizer.analyze_issue("## Tasks\n- [ ] Add tests", use_llm=True)
    assert result.provider_used is None

    primary_chain = mock.MagicMock()
    primary_chain.invoke.side_effect = RuntimeError("rate limited")
    mock_template = mock.MagicMock()
    mock_template.__or__ = mock.MagicMock(return_value=primary_chain)

    class FakeChatPromptTemplate:
        @staticmethod
        def from_template(_: str):
            return mock_template

    fake_prompts = types.SimpleNamespace(ChatPromptTemplate=FakeChatPromptTemplate)
    monkeypatch.setitem(sys.modules, "langchain_core", types.SimpleNamespace(prompts=fake_prompts))
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", fake_prompts)
    monkeypatch.setattr(
        issue_optimizer,
        "_get_llm_client",
        mock.MagicMock(return_value=(mock.MagicMock(), "openai")),
    )
    monkeypatch.setattr("tools.llm_provider._is_token_limit_error", lambda _error: False)
    monkeypatch.setenv("ISSUE_NUMBER", "99")
    result = issue_optimizer.analyze_issue("## Tasks\n- [ ] Add tests", use_llm=True)
    assert result.provider_used is None
    assert "LLM analysis failed" in capsys.readouterr().err

    apply_result = issue_optimizer.apply_suggestions(
        "## Tasks\n- [ ] Keep\n\n## Acceptance Criteria\n- [ ] pytest",
        {},
        use_llm=True,
    )
    assert apply_result["used_llm"] is False
    assert "LLM apply failed" in capsys.readouterr().err


def test_openai_retry_surfaces_validation_error_and_duplicated_sections(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    primary_chain = mock.MagicMock()
    primary_chain.invoke.side_effect = RuntimeError("token limit")
    openai_chain = mock.MagicMock()
    openai_chain.invoke.return_value = _response_with("{not-valid-json")
    mock_template = mock.MagicMock()
    mock_template.__or__ = mock.MagicMock(side_effect=[primary_chain, openai_chain])

    class FakeChatPromptTemplate:
        @staticmethod
        def from_template(_: str):
            return mock_template

    fake_prompts = types.SimpleNamespace(ChatPromptTemplate=FakeChatPromptTemplate)
    monkeypatch.setitem(sys.modules, "langchain_core", types.SimpleNamespace(prompts=fake_prompts))
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", fake_prompts)
    monkeypatch.setattr(
        issue_optimizer,
        "_get_llm_client",
        mock.MagicMock(
            side_effect=[
                (mock.MagicMock(), "github-models"),
                (mock.MagicMock(), "openai"),
            ]
        ),
    )
    monkeypatch.setattr("tools.llm_provider._is_token_limit_error", lambda _error: True)
    result = issue_optimizer.analyze_issue("Issue body", use_llm=True)
    assert result.provider_used is None
    err = capsys.readouterr().err
    assert "LLM output failed validation" in err or "Fallback analysis used" in (
        result.overall_notes or ""
    )

    primary_chain = mock.MagicMock()
    primary_chain.invoke.side_effect = RuntimeError("token limit")
    openai_chain = mock.MagicMock()
    openai_chain.invoke.return_value = _response_with(
        "## Tasks\n- [ ] A\n## Tasks\n- [ ] B\n## Acceptance Criteria\n- [ ] ok"
    )
    mock_template = mock.MagicMock()
    mock_template.__or__ = mock.MagicMock(side_effect=[primary_chain, openai_chain])
    monkeypatch.setattr(
        issue_optimizer,
        "_get_llm_client",
        mock.MagicMock(
            side_effect=[
                (mock.MagicMock(), "github-models"),
                (mock.MagicMock(), "openai"),
            ]
        ),
    )
    applied = issue_optimizer.apply_suggestions("Issue body", {}, use_llm=True)
    assert applied["used_llm"] is False
    assert "duplicated sections" in capsys.readouterr().err


def test_cli_json_apply_includes_guard_and_trace_fields(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        issue_optimizer,
        "apply_suggestions",
        lambda *_a, **_k: {
            "formatted_body": "## Tasks\n- [ ] x\n\n## Acceptance Criteria\n- [ ] y",
            "provider_used": "openai",
            "used_llm": True,
            "guard_blocked": True,
            "guard_reason": "injection",
            "langsmith_trace_id": "tid",
            "langsmith_trace_url": "https://example.test/t",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "issue_optimizer.py",
            "--input-text",
            "body",
            "--apply-suggestions",
            "--suggestions-json",
            "{}",
            "--json",
        ],
    )
    issue_optimizer.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["guard_blocked"] is True
    assert payload["langsmith_trace_id"] == "tid"
    assert payload["langsmith_trace_url"] == "https://example.test/t"

    assert (
        issue_optimizer._load_suggestions(
            argparse.Namespace(
                suggestions_json="{bad",
                suggestions_file=None,
                suggestions_comment_file=None,
                suggestions_comment_text=None,
            )
        )
        is None
    )
