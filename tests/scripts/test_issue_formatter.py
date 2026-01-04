from __future__ import annotations

from scripts.langchain import issue_formatter


def _extract_section(body: str, heading: str) -> str:
    marker = f"## {heading}"
    if marker not in body:
        return ""
    parts = body.split(marker, 1)[1].split("\n")
    # Skip the blank line after the heading
    content_lines = []
    for line in parts[1:]:
        if line.startswith("## "):
            break
        content_lines.append(line)
    return "\n".join(content_lines).strip()


def test_format_issue_fallback_adds_sections_and_checkboxes() -> None:
    raw = """Why:
We need to improve the issue intake.

Tasks:
- add formatter
- add tests

Acceptance Criteria:
- formatted issue body
- label transition works
"""
    result = issue_formatter.format_issue_body(raw, use_llm=False)
    formatted = result["formatted_body"]

    assert "## Why" in formatted
    assert "## Tasks" in formatted
    assert "## Acceptance Criteria" in formatted
    assert "- [ ] add formatter" in formatted
    assert "- [ ] add tests" in formatted
    assert "- [ ] formatted issue body" in formatted
    assert "- [ ] label transition works" in formatted


def test_format_issue_fallback_strips_bullets_from_scope() -> None:
    raw = """## Scope
- keep API stable
- avoid workflow changes

## Tasks
- add formatter
"""
    result = issue_formatter.format_issue_body(raw, use_llm=False)
    formatted = result["formatted_body"]

    scope = _extract_section(formatted, "Scope")
    assert scope
    assert "- " not in scope
    assert "* " not in scope
    assert "keep API stable" in scope
    assert "avoid workflow changes" in scope


def test_format_issue_fallback_uses_placeholders() -> None:
    raw = "Just a note without sections."
    result = issue_formatter.format_issue_body(raw, use_llm=False)
    formatted = result["formatted_body"]

    tasks = _extract_section(formatted, "Tasks")
    acceptance = _extract_section(formatted, "Acceptance Criteria")

    assert tasks == "- [ ] _Not provided._"
    assert acceptance == "- [ ] _Not provided._"
