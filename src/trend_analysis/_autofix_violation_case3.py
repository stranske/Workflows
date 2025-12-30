"""Autofix fixture with basic arithmetic helpers."""

from __future__ import annotations

from collections.abc import Sequence


def compute_sum(left: int, right: int) -> int:
    return left + right


def list_builder(values: list[int]) -> list[int]:
    return list(values)


def ambiguous_types(left: Sequence[int], right: Sequence[int]) -> list[int]:
    return [a + b for a, b in zip(left, right, strict=True)]


class SomeContainer:
    def __init__(self, values: list[int]) -> None:
        self._values = values

    def total(self) -> int:
        return sum(self._values)
