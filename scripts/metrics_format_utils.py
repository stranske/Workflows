#!/usr/bin/env python3
"""Utility functions for metrics formatting.

This module provides helper functions for formatting metrics output.
"""


def format_percentage(value: float, decimals: int = 1) -> str:
    """Format a float as a percentage string."""
    return f"{value:.{decimals}f}%"


def format_count(count: int, singular: str, plural: str = None) -> str:
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


def ascii_sparkline(series: list[float], steps: str = " .:-=+*#%@") -> str:
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
