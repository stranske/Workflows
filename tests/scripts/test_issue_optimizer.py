from __future__ import annotations

from scripts.langchain import issue_optimizer


def test_extract_suggestions_json_from_comment() -> None:
    comment = """
Here are the suggestions:
<!-- suggestions-json: {"blocked_tasks": [{"task": "Update workflow", "reason": "Protected", "suggested_action": "Ask human"}]} -->
"""
    payload = issue_optimizer._extract_suggestions_json(comment)
    assert payload is not None
    assert payload["blocked_tasks"][0]["task"] == "Update workflow"


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
