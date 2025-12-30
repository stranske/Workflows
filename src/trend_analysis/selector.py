"""Selection helpers for ranking fixtures."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class RankSelector:
    top_n: int
    rank_column: str

    def select(self, frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return the top-ranked rows and the remaining frame."""
        ranked = frame.sort_values(self.rank_column, ascending=False)
        selected = ranked.head(self.top_n)
        remainder = ranked.iloc[self.top_n :]
        return selected, remainder
