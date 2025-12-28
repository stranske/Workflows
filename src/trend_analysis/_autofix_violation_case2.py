"""Simplified autofix case for return-type and formatting checks."""

from __future__ import annotations

from collections.abc import Iterable


def _payload(values: Iterable[int]) -> dict[str, float | int]:
    items = list(values)
    total = sum(items)
    count = len(items)
    mean = total / count if count else 0
    return {"total": total, "mean": mean, "count": count}


def compute(values: Iterable[int] | None = None) -> dict[str, float | int]:
    return _payload(values or [1, 2, 3])


class Example:
    def method(self, value: float, offset: float) -> float:
        return value + offset


def long_line_function() -> str:
    return "An extravagantly elongated string intended to trigger formatting rules."


def unused_func(a: int, b: int, c: int) -> None:  # noqa: ARG001
    return None


if __name__ == "__main__":
    print(compute())
