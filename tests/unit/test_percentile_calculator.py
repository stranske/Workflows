from __future__ import annotations

import pytest

from src import percentile_calculator


def test_percentiles_small_dataset() -> None:
    values = [1.0, 2.0, 3.0, 4.0]
    sorted_values = sorted(values)

    assert percentile_calculator.percentile(sorted_values, 50) == pytest.approx(2.5)
    assert percentile_calculator.percentile(sorted_values, 90) == pytest.approx(3.7)
    assert percentile_calculator.percentile(sorted_values, 99) == pytest.approx(3.97)


def test_percentile_bounds_and_single_value() -> None:
    assert percentile_calculator.percentile([10.0], 50) == 10.0
    assert percentile_calculator.percentile([1.0, 2.0], 0) == 1.0
    assert percentile_calculator.percentile([1.0, 2.0], 100) == 2.0


def test_summarize_values_empty() -> None:
    summary = percentile_calculator.summarize_values([])

    assert summary == {"mean": None, "p50": None, "p90": None, "p99": None}
