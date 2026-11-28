"""Helpers that mimic simple aggregation behavior."""

from __future__ import annotations

from collections.abc import Iterable


def aggregate_numbers(values: Iterable[int]) -> str:
    """Join numbers with a pipe separator for autofix regression tests."""
    return " | ".join(str(value) for value in values)
