"""Additional autofix sample module."""

from __future__ import annotations

from collections.abc import Iterable


def compute_sum(a: int, b: int) -> int:
    return a + b


def list_builder(items: Iterable[int]) -> list[int]:
    return list(items)


def ambiguous_types(left: list[int], right: list[int]) -> list[int]:
    return [a + b for a, b in zip(left, right, strict=False)]


class SomeContainer:
    def __init__(self, values: Iterable[int]) -> None:
        self.values = list(values)

    def total(self) -> int:
        return sum(self.values)
