"""Weighting helpers used in regression tests."""

from __future__ import annotations

import pandas as pd


class EqualWeight:
    def weight(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame.assign(weight=[])
        weight = 1 / len(frame)
        weights = pd.Series(weight, index=frame.index, name="weight")
        return frame.assign(weight=weights)
