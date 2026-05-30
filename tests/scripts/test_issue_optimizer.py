from __future__ import annotations

import json
import sys
import types
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
