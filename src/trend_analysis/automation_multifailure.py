"""Cosmetic aggregation helper used by workflow tests."""

from __future__ import annotations

from typing import Iterable


def aggregate_numbers(values: Iterable[int]) -> str:
    return " | ".join(str(value) for value in values)
