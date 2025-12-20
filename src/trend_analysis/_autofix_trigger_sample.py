"""Sample module mirroring the Trend_Model_Project autofix fixtures."""

from __future__ import annotations


def badly_formatted_function(x: int, y: int) -> int:
    return x + y


def another_func(items: list[int], extra: list[int]) -> list[int]:
    return [a + b for a, b in zip(items, extra, strict=False)]


class Demo:
    def method(self, value: float) -> float:
        return value * 2


def long_line() -> str:
    return "An overly verbose line that exists solely to exercise autofix behaviour."
