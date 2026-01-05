from __future__ import annotations

from scripts.langchain import issue_optimizer


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
    assert "Updated WORKFLOW_OUTPUTS.md suggestions-json:" in comment


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
    assert "<!-- Updated WORKFLOW_OUTPUTS.md suggestions-json:" in comment


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
