from __future__ import annotations

from importlib import import_module


def test_demo_autofix_probe_returns_input() -> None:
    module = import_module("trend_analysis._autofix_probe")
    values = [1, 2, 3]
    result = module.demo_autofix_probe(values)
    assert list(result) == values
    assert result is values
