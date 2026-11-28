"""Utilities for percentile calculations.

This module uses a linear interpolation approach between adjacent ranks.
For a percentile $p$ in $[0, 100]$ and sorted values of length $n$:

$$
\text{rank} = \frac{p}{100} (n - 1)
$$

The result is linearly interpolated between the lower and upper ranks. This
matches the "linear" interpolation method used by common statistics tools.
"""

from __future__ import annotations

import math
from collections.abc import Iterable


def percentile(sorted_values: list[float], percentile_value: float) -> float | None:
    """Return the percentile using linear interpolation between ranks."""
    if not sorted_values:
        return None
    if percentile_value <= 0:
        return sorted_values[0]
    if percentile_value >= 100:
        return sorted_values[-1]
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (percentile_value / 100) * (len(sorted_values) - 1)
    lower_index = int(math.floor(rank))
    upper_index = int(math.ceil(rank))
    if lower_index == upper_index:
        return sorted_values[lower_index]
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    weight = rank - lower_index
    return lower_value + (upper_value - lower_value) * weight


def summarize_values(values: Iterable[float]) -> dict[str, float | None]:
    """Summarize values with mean and p50/p90/p99 percentiles."""
    values_list = list(values)
    if not values_list:
        return {"mean": None, "p50": None, "p90": None, "p99": None}
    sorted_values = sorted(values_list)
    mean_value = sum(sorted_values) / len(sorted_values)
    return {
        "mean": mean_value,
        "p50": percentile(sorted_values, 50),
        "p90": percentile(sorted_values, 90),
        "p99": percentile(sorted_values, 99),
    }
