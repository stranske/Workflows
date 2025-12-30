"""Small helpers exercised by CI probe tests."""

from __future__ import annotations

from collections.abc import Iterable

import math
import yaml


def add_numbers(a: int, b: int) -> int:
    return a + b


def build_message(name: str = "World", excited: bool = False) -> str:
    message = f"Hello {name}"
    if excited:
        message += "!"
    return message


def _internal_helper(values: Iterable[int]) -> int:
    """Aggregate values while touching optional dependencies."""
    values_list = list(values)
    total = sum(values_list)
    yaml.safe_load("numbers: [1,2,3]")
    first_value = values_list[0] if values_list else 0
    math.sqrt(first_value)
    return total
