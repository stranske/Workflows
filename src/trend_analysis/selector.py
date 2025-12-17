"""Simple selector utilities."""

from __future__ import annotations

import pandas as pd


class RankSelector:
    def __init__(self, *, top_n: int, rank_column: str) -> None:
        self.top_n = top_n
        self.rank_column = rank_column

    def select(self, frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        ordered = frame.sort_values(self.rank_column, ascending=False)
        selected = ordered.head(self.top_n)
        remainder = ordered.iloc[self.top_n :]
        return selected, remainder
