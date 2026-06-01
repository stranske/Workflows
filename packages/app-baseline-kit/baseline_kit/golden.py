"""Golden-master glue over pytest-regressions.

Apps reduce a run to a flat metrics dict and pass it here; the baseline is
stored on disk and diffed with float tolerance. Re-bless with ``--force-regen``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULT_TOLERANCE = {"atol": 1e-9, "rtol": 1e-6}


def check_metrics(
    num_regression: Any, metrics: Mapping[str, float], tolerance: Mapping[str, float] | None = None
) -> None:
    """Golden-master a flat dict of scalar metrics via the num_regression fixture."""
    num_regression.check(
        {str(k): [float(v)] for k, v in metrics.items()},
        default_tolerance=tolerance or DEFAULT_TOLERANCE,
    )
