"""Tests for generate_llm_workflow_update_comment helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.generate_llm_workflow_update_comment import (
    _build_label_line,
    _build_main_body,
    _build_notes_section,
    _build_workflows_section,
    _escape_markdown,
    build_comment,
)


def test_build_comment_includes_label_and_requirements() -> None:
    comment = build_comment(include_label=True)

    assert "Label: needs-human" in comment
    assert ".github/workflows/agents-auto-pilot.yml" in comment
    assert ".github/workflows/agents-issue-optimizer.yml" in comment
    assert ".github/workflows/reusable-agents-verifier.yml" in comment
    assert "pip install -r tools/requirements-llm.txt" in comment
    assert "pip install -r .workflows-lib/tools/requirements-llm.txt" in comment
    assert "actions/cache@v4" in comment
    assert "langchain" in comment
    assert "agent-high-privilege" in comment


def test_build_comment_lists_default_workflows() -> None:
    comment = build_comment()

    assert "Affected workflows:" in comment
    assert "- .github/workflows/agents-auto-pilot.yml" in comment
    assert "- .github/workflows/agents-issue-optimizer.yml" in comment
    assert "- .github/workflows/reusable-agents-verifier.yml" in comment


def test_build_comment_preserves_output_without_notes() -> None:
    """Verify backward compatibility: output unchanged when notes not provided."""
    comment = build_comment(include_label=True)

    # Verify structure is preserved
    lines = comment.split("\n")
    assert lines[0] == "Label: needs-human"
    assert "Workflow updates required" in comment
    assert "Affected workflows:" in comment
    assert "- .github/workflows/agents-auto-pilot.yml" in comment
    assert "- .github/workflows/agents-issue-optimizer.yml" in comment
    assert "- .github/workflows/reusable-agents-verifier.yml" in comment
    # Verify no notes section is added
    assert "Notes:" not in comment


def test_build_comment_with_empty_notes() -> None:
    """Test that empty notes don't add extra content."""
    comment_without_notes = build_comment()
    comment_with_empty_notes = build_comment(notes="")
    comment_with_none_notes = build_comment(notes=None)

    assert comment_without_notes == comment_with_empty_notes
    assert comment_without_notes == comment_with_none_notes


def test_build_comment_with_multiline_notes() -> None:
    """Test that multiline notes are properly formatted."""
    notes = "First line\nSecond line\nThird line"
    comment = build_comment(notes=notes)

    assert "Notes: First line" in comment
    assert "  Second line" in comment
    assert "  Third line" in comment


def test_build_comment_with_markdown_sensitive_repo_names() -> None:
    """Test workflow names containing Markdown-sensitive characters."""
    markdown_sensitive_paths = [
        Path(".github/workflows/*special*_workflow.yml"),
        Path(".github/workflows/[test]_workflow.yml"),
        Path(".github/workflows/workflow_with_#_hash.yml"),
        Path(".github/workflows/workflow_with_*_asterisk.yml"),
        Path(".github/workflows/workflow_with__underscore.yml"),
    ]

    comment = build_comment(workflows=markdown_sensitive_paths)

    # All paths should be present in escaped form
    for path in markdown_sensitive_paths:
        path_str = str(path)
        escaped_path = _escape_markdown(path_str)
        # Check that the escaped path appears in the comment
        assert escaped_path in comment, f"Expected {escaped_path!r} in comment"

    # Verify the affected workflows section exists
    assert "Affected workflows:" in comment
    # Verify that unescaped special characters are NOT present in the workflow list
    assert "*special*" not in comment
    assert "[test]" not in comment


def test_escape_markdown_basic() -> None:
    """Test basic markdown escaping."""
    assert _escape_markdown("*test*") == "\\*test\\*"
    assert _escape_markdown("[test]") == "\\[test\\]"
    assert _escape_markdown("#test") == "\\#test"
    assert _escape_markdown("_test_") == "\\_test\\_"


def test_escape_markdown_preserves_safe_text() -> None:
    """Test that safe text is preserved."""
    # Text with no markdown-sensitive characters
    safe_text = "normal-text-123.txt"
    assert _escape_markdown(safe_text) == safe_text


def test_build_label_line_with_label() -> None:
    """Test label line generation."""
    assert _build_label_line(True) == ["Label: needs-human"]
    assert _build_label_line(False) == []


def test_build_main_body() -> None:
    """Test main body generation."""
    body = _build_main_body()
    assert "Workflow updates required" in body
    assert ".github/workflows/agents-issue-optimizer.yml" in body
    assert "pip install -r tools/requirements-llm.txt" in body
    assert "agent-high-privilege" in body


def test_build_workflows_section() -> None:
    """Test workflows section generation."""
    workflows = [Path(".github/workflows/test.yml")]
    section = _build_workflows_section(workflows)

    assert len(section) == 2
    assert section[0] == "Affected workflows:"
    assert section[1] == "- .github/workflows/test.yml"


def test_build_notes_section() -> None:
    """Test notes section generation."""
    # None notes
    assert _build_notes_section(None) == []

    # Empty notes
    assert _build_notes_section("") == []

    # Single line notes
    result = _build_notes_section("Test note")
    assert result == ["Notes: Test note"]

    # Multiline notes
    result = _build_notes_section("Line 1\nLine 2")
    assert result == ["Notes: Line 1", "  Line 2"]


def test_build_comment_with_notes_and_label() -> None:
    """Test full integration with notes and label."""
    comment = build_comment(
        include_label=True,
        notes="Additional context\nMore details",
    )

    assert "Label: needs-human" in comment
    assert "Notes: Additional context" in comment
    assert "  More details" in comment
    assert "Affected workflows:" in comment
