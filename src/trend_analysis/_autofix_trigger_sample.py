"""Sample module used to exercise autofix flows."""

from __future__ import annotations


def badly_formatted_function(left: int, right: int) -> int:
    return left + right


def another_func(left: list[int], right: list[int]) -> list[int]:
    return [a + b for a, b in zip(left, right, strict=True)]


def long_line() -> str:
    return "This is an overly verbose line that exists for autofix demonstrations."


class Demo:
    def method(self, value: float) -> float:
        return value * 2
