from __future__ import annotations

from scripts.langchain import context_extractor


def test_extract_context_fallback_collects_entries() -> None:
    issue_body = """## Scope
We must keep the API stable.
Constraint: avoid workflow edits.

## Tasks
- [ ] update docs

Related: #123 and org/repo#45.
See https://example.com/spec.

Blocked by infra rollout.
"""
    comments = ["Depends on PR #99 for the API change."]
    result = context_extractor.extract_context(issue_body, comments=comments, use_llm=False)
    context = result["context_section"]

    assert "## Context for Agent" in context
    assert "### Design Decisions & Constraints" in context
    assert "We must keep the API stable." in context
    assert "Constraint: avoid workflow edits." in context
    assert "### Related Issues/PRs" in context
    assert "#123" in context
    assert "org/repo#45" in context
    assert "#99" in context
    assert "### References" in context
    assert "https://example.com/spec" in context
    assert "### Blockers & Dependencies" in context
    assert "Blocked by infra rollout." in context
    assert "update docs" not in context


def test_extract_context_fallback_returns_empty_when_no_context() -> None:
    issue_body = """## Tasks
- [ ] implement feature
"""
    result = context_extractor.extract_context(issue_body, use_llm=False)
    assert result["context_section"] == ""
