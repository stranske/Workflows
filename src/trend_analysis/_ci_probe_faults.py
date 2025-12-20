"""Probe helper exercising lightweight dependencies."""

from __future__ import annotations

import json
import math
from typing import Iterable

import yaml


def add_numbers(a: int, b: int) -> int:
    return a + b


def build_message(*, name: str | None = None, excited: bool = False) -> str:
    base = f"Hello {name}" if name else "Hello World"
    return f"{base}!" if excited else base


def _internal_helper(values: Iterable[int]) -> int:
    yaml.safe_load("numbers: [1,2,3]")
    items = list(values)
    math.sqrt(items[0] if items else 0)
    return sum(items)


def _main() -> int:
    payload = {"sum": _internal_helper([1, 2, 3])}
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
