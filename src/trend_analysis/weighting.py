"""Weighting strategies for sample data."""

from __future__ import annotations

import pandas as pd


class EqualWeight:
    """Assign equal weights across a frame."""

    def weight(self, frame: pd.DataFrame) -> pd.DataFrame:
        count = len(frame.index)
        if count == 0:
            weights = pd.Series(dtype=float)
        else:
            weights = pd.Series([1.0 / count] * count, index=frame.index)
        result = frame.copy()
        result["weight"] = weights
        return result
