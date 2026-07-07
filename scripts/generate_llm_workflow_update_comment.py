#!/usr/bin/env python3
"""Generate a needs-human comment for LLM workflow update requirements."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path

DEFAULT_WORKFLOWS = (
    Path(".github/workflows/agents-auto-pilot.yml"),
    Path(".github/workflows/agents-issue-optimizer.yml"),
    Path(".github/workflows/reusable-agents-verifier.yml"),
)


def _escape_markdown(text: str) -> str:
    """Escape Markdown-sensitive characters in text for safe display.

    Escapes characters that have special meaning in Markdown to prevent
    unintended formatting in the rendered comment. Only escapes characters
    that can cause issues when appearing inline (not at start of line).
    """
    # Characters that need escaping in inline contexts:
    # * and _ for emphasis
    # [ ] ( ) for links
    # # for headings (though less likely inline)
    # ! for images
    # Backslash must be first to avoid double-escaping
    escape_map = {
        "\\": "\\\\",
        "*": "\\*",
        "_": "\\_",
        "[": "\\[",
        "]": "\\]",
        "(": "\\(",
        ")": "\\)",
        "#": "\\#",
        "!": "\\!",
    }

    result = text
    for char, escaped in escape_map.items():
        result = result.replace(char, escaped)
    return result


def _build_label_line(include_label: bool) -> list[str]:
    """Build the label line if requested."""
    if include_label:
        return ["Label: needs-human"]
    return []


def _build_main_body() -> str:
    """Build the main instruction body of the comment."""
    return (
        "Workflow updates required in .github/workflows/agents-auto-pilot.yml, "
        ".github/workflows/agents-issue-optimizer.yml, and "
        ".github/workflows/reusable-agents-verifier.yml. Add pinned installs "
        "(`python -m pip install -r tools/requirements-llm.txt` and "
        "`pip install -r .workflows-lib/tools/requirements-llm.txt` for evaluate/compare), "
        "add actions/cache@v4 pip cache keyed by requirements hash + Python version, "
        "and remove any floating `pip install langchain*` lines. Workflow edits require "
        "agent-high-privilege."
    )


def _build_workflows_section(workflows: Iterable[Path]) -> list[str]:
    """Build the affected workflows section."""
    lines = ["Affected workflows:"]
    for workflow in workflows:
        # Escape markdown-sensitive characters in the workflow path
        escaped_path = _escape_markdown(str(workflow))
        lines.append(f"- {escaped_path}")
    return lines


def _build_notes_section(notes: str | None) -> list[str]:
    """Build the notes section if notes are provided."""
    if not notes:
        return []
    # Escape markdown-sensitive characters in notes
    escaped_notes = _escape_markdown(notes)
    # Preserve newlines by splitting and escaping each line
    note_lines = escaped_notes.split("\n")
    return [f"Notes: {line}" if i == 0 else f"  {line}" for i, line in enumerate(note_lines)]


def build_comment(
    workflows: Iterable[Path] = DEFAULT_WORKFLOWS,
    include_label: bool = False,
    notes: str | None = None,
) -> str:
    """Build the complete comment string from components.

    Args:
        workflows: Iterable of Path objects for affected workflows.
        include_label: Whether to include the "Label: needs-human" line.
        notes: Optional additional notes text (can be multiline).

    Returns:
        The assembled comment as a single string.
    """
    lines: list[str] = []
    lines.extend(_build_label_line(include_label))
    lines.append(_build_main_body())
    lines.append("")
    lines.extend(_build_workflows_section(workflows))

    notes_lines = _build_notes_section(notes)
    if notes_lines:
        lines.append("")
        lines.extend(notes_lines)

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workflow",
        action="append",
        type=Path,
        dest="workflows",
        help="Path to a workflow YAML file (repeatable). Defaults to the LLM workflows.",
    )
    parser.add_argument(
        "--include-label",
        action="store_true",
        help="Include needs-human label line in the output.",
    )
    parser.add_argument(
        "--notes",
        type=str,
        default=None,
        help="Optional additional notes text (can be multiline).",
    )
    args = parser.parse_args()
    workflows = tuple(args.workflows) if args.workflows else DEFAULT_WORKFLOWS
    print(
        build_comment(
            workflows=workflows,
            include_label=args.include_label,
            notes=args.notes,
        )
    )


if __name__ == "__main__":
    main()
