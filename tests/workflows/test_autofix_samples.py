from __future__ import annotations

import ast
import runpy
import sys  # Added: required for module cache manipulation in script test

import pytest

from trend_analysis import (
    _autofix_trigger_sample,
    _autofix_violation_case2,
    _autofix_violation_case3,
)


def test_trigger_sample_functions_behave_as_documented() -> None:
    assert _autofix_trigger_sample.badly_formatted_function(3, 7) == 10
    assert _autofix_trigger_sample.another_func([1, 2], [3, 4]) == [4, 6]
    assert _autofix_trigger_sample.Demo().method(1.5) == 3.0
    assert "overly verbose" in _autofix_trigger_sample.long_line()


def test_violation_case2_compute_and_helpers() -> None:
    payload = _autofix_violation_case2.compute([2, 4, 6])
    assert payload == {"total": 12, "mean": 4.0, "count": 3}

    # Exercise the default branch and the intentionally "unused" helper.
    default_payload = _autofix_violation_case2.compute()
    assert default_payload == {"total": 6, "mean": 2.0, "count": 3}

    assert _autofix_violation_case2.Example().method(3.5, 0.5) == 4.0
    assert "extravagantly" in _autofix_violation_case2.long_line_function()
    assert _autofix_violation_case2.unused_func(1, 2, 3) is None


def test_violation_case2_runs_as_script(capsys: "pytest.CaptureFixture[str]") -> None:
    """Ensure the module's ``__main__`` branch emits the expected payload."""

    module_name = "trend_analysis._autofix_violation_case2"

    # Guard: ensure module is present before popping; capture original for restoration
    original = sys.modules.get(module_name)
    sys.modules.pop(module_name, None)

    try:
        runpy.run_module(module_name, run_name="__main__")
    finally:
        if original is not None:
            sys.modules[module_name] = original

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "'total': 6" in captured.out
    assert "'mean': 2.0" in captured.out
    assert "'count': 3" in captured.out


def test_violation_case2_runs_as_a_script(capsys) -> None:
    sys.modules.pop("trend_analysis._autofix_violation_case2", None)
    runpy.run_module("trend_analysis._autofix_violation_case2", run_name="__main__")

    captured = capsys.readouterr()
    output = ast.literal_eval(captured.out.strip())
    assert output == {"total": 6, "mean": 2.0, "count": 3}


def test_violation_case3_exposes_expected_behaviour() -> None:
    assert _autofix_violation_case3.compute_sum(5, 7) == 12
    assert _autofix_violation_case3.list_builder([1, 2, 3]) == [1, 2, 3]
    assert _autofix_violation_case3.ambiguous_types([1, 2], [4, 6]) == [5, 8]

    container = _autofix_violation_case3.SomeContainer([2, 3, 5])
    assert container.total() == 10
