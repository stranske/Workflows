#!/usr/bin/env python3
"""Utility functions for metrics formatting.

This module provides helper functions for formatting metrics output.
"""

from typing import Dict, List


def format_percentage(value: float, decimals: int = 1) -> str:
    """Format a float as a percentage string."""
    return f"{value:.{decimals}f}%"


def format_count(count: int, singular: str, plural: str = None) -> str:
    """Format a count with appropriate singular/plural label."""
    if plural is None:
        plural = singular + "s"
    label = singular if count == 1 else plural
    return f"{count} {label}"


def summarize_patterns(patterns: Dict[str, int]) -> List[str]
    """Summarize failure patterns as formatted strings."""
    if not patterns:
        return []
    
    sorted_patterns = sorted(patterns.items(), key=lambda x: x[1], reverse=True)
    return [f"{reason}: {count}" for reason, count in sorted_patterns]


def truncate_string(text: str, max_length: int = 50) -> str:
    """Truncate a string to max_length, adding ellipsis if needed."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."
