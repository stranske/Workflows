"""Probe module used by autofix tests."""

from __future__ import annotations

from collections.abc import Iterable


def demo_autofix_probe(values: Iterable[object]) -> Iterable[object]:
    """Return the input iterable unchanged."""

    return values
