#!/usr/bin/env python3
"""Utility functions for metrics formatting.

This module provides helper functions for formatting metrics output.
"""


def format_percentage(value: float, decimals: int = 1) -> str:
    """Format a float as a percentage string."""
    return f"{value:.{decimals}f}%"


def format_count(count: int, singular: str, plural: str | None = None) -> str:
    """Format a count with appropriate singular/plural label."""
    if plural is None:
        plural = singular + "s"
    label = singular if count == 1 else plural
    return f"{count} {label}"


def summarize_patterns(patterns: dict[str, int]) -> list[str]:
    """Summarize failure patterns as formatted strings."""
    if not patterns:
        return []

    sorted_patterns = sorted(patterns.items(), key=lambda x: x[1], reverse=True)
    return [f"{reason}: {count}" for reason, count in sorted_patterns]


def truncate_string(text: str, max_length: int = 50) -> str:
    """Truncate a string to max_length, adding ellipsis if needed."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _normalize_markdown_cell(value: object) -> str:
    """Prepare a value for safe Markdown table rendering."""
    text = "" if value is None else str(value)
    if "|" in text:
        text = text.replace("|", r"\|")
    if "\n" in text:
        text = text.replace("\n", "<br>")
    return text


def _alignment_marker(alignment: str) -> str:
    """Convert alignment keywords into Markdown table markers."""
    alignment_key = alignment.strip().lower()
    if alignment_key in {"left", "l"}:
        return "---"
    if alignment_key in {"center", "c"}:
        return ":---:"
    if alignment_key in {"right", "r"}:
        return "---:"
    raise ValueError(f"Unsupported alignment: {alignment}")


def format_markdown_table(
    headers: list[str],
    rows: list[list[object]],
    alignments: list[str] | None = None,
) -> str:
    """Format a Markdown table with optional alignment hints."""
    if not headers:
        return ""
    column_count = len(headers)
    if alignments is None:
        alignments = ["left"] * column_count
    if len(alignments) != column_count:
        raise ValueError("Alignment list must match header length.")

    header_cells = [_normalize_markdown_cell(header) for header in headers]
    alignment_cells = [_alignment_marker(alignment) for alignment in alignments]

    lines = [
        f"| {' | '.join(header_cells)} |",
        f"| {' | '.join(alignment_cells)} |",
    ]

    for row in rows:
        if len(row) != column_count:
            raise ValueError("Row length must match header length.")
        row_cells = [_normalize_markdown_cell(cell) for cell in row]
        lines.append(f"| {' | '.join(row_cells)} |")

    return "\n".join(lines)


def ascii_sparkline(series: list[float], steps: str = ".:-=+*#%@") -> str:
    """Render a compact ASCII trend chart for a numeric series."""
    if not series:
        return ""
    min_value = min(series)
    max_value = max(series)
    if max_value == min_value:
        return steps[0] * len(series)
    span = max_value - min_value
    max_index = len(steps) - 1
    chars: list[str] = []
    for value in series:
        normalized = (value - min_value) / span
        index = int(normalized * max_index)
        if index < 0:
            index = 0
        elif index > max_index:
            index = max_index
        chars.append(steps[index])
    return "".join(chars)
