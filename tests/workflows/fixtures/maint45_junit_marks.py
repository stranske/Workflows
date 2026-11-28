"""Explicit pytest inputs for the Maint 45 original-JUnit integration test."""

import pytest


@pytest.mark.cosmetic
def test_cosmetic_marker() -> None:
    """Produce a JUnit case with a function-level cosmetic mark."""


def test_unmarked_control() -> None:
    """Produce a JUnit case without a mark in the same source file."""
