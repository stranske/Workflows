"""Autofix fixture that intentionally includes minor issues."""

from __future__ import annotations

from collections.abc import Iterable


def compute(values: Iterable[int] | None = None) -> dict[str, float | int]:
    numbers = list(values) if values is not None else [1, 2, 3]
    total = sum(numbers)
    count = len(numbers)
    mean = total / count if count else 0.0
    return {"total": total, "mean": float(mean), "count": count}


def long_line_function() -> str:
    return "An extravagantly long sentence exists here solely for autofix coverage."


def unused_func(*_args: int) -> None:
    return None


class Example:
    def method(self, left: float, right: float) -> float:
        return left + right


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    print(compute())
