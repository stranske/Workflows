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
                    "Add tests and update docs",
                    "Depends on backend merge",
                ],
            }
        ]
    }
    result = issue_optimizer.apply_suggestions(issue_body, suggestions, use_llm=False)
    formatted = result["formatted_body"].lower()
    assert "  - [ ] add tests" in formatted
    assert "  - [ ] update docs" in formatted
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
    mock_chain.invoke.assert_called_once_with(expected_prompt)
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


def test_detect_blocked_and_subjective_criteria() -> None:
    blocked = issue_optimizer._detect_blocked_tasks(
        ["Edit .github/workflows/ci.yml", "Raise coverage to 80%"]
    )
    assert blocked[0]["reason"] == "Requires workflow changes, which are protected"
    assert blocked[1]["suggested_action"] == "Convert to adding tests and report achieved coverage"

    criteria = issue_optimizer._detect_objective_criteria(["Make output nice"])
    assert criteria[0]["issue"] == "Subjective wording"


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

    def fake_normalize(items: list[str]) -> list[str]:
        return [item.lower() for item in items]

    monkeypatch.setattr(
        "scripts.langchain.task_decomposer.decompose_task",
        fake_decompose,
    )
    monkeypatch.setattr(
        "scripts.langchain.task_decomposer.normalize_subtasks",
        fake_normalize,
    )
    task_splitting = [{"task": "Large task", "split_suggestions": []}]
    updated = issue_optimizer._ensure_task_decomposition(task_splitting, use_llm=True)
    assert updated[0]["split_suggestions"] == ["one", "two"]


def test_apply_task_decomposition_skips_when_missing_header() -> None:
    formatted = "## Scope\n- item"
    suggestions = {
        "task_splitting": [
            {"task": "Update docs", "split_suggestions": ["Write docs", "Review docs"]}
        ]
    }
    updated = issue_optimizer._apply_task_decomposition(formatted, suggestions)
    assert updated == formatted


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
