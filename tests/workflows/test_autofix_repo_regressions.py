from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yaml

from trend_analysis.automation_multifailure import aggregate_numbers
from trend_analysis.constants import NUMERICAL_TOLERANCE_MEDIUM
from trend_analysis.selector import RankSelector
from trend_analysis.weighting import EqualWeight

EXPECTED_AUTOFIX_SELECTED_FUNDS = 2
EXPECTED_AGGREGATE_OUTPUT = "1 | 2 | 3"


def _load_score_frame() -> pd.DataFrame:
    path = Path("tests/fixtures/score_frame_2025-06-30.csv")
    return pd.read_csv(path, index_col=0)


def compute_expected_autofix_selected_funds() -> int:
    frame = _load_score_frame()
    selector = RankSelector(top_n=2, rank_column="Sharpe")
    selected, _ = selector.select(frame)
    return len(selected)


def _optional_passthrough(value: Optional[int]) -> int:
    if value is None:
        return 0
    return value


def test_autofix_selected_funds_constant() -> None:
    frame = _load_score_frame()
    selector = RankSelector(top_n=2, rank_column="Sharpe")
    selected, _ = selector.select(frame)
    assert len(selected) == EXPECTED_AUTOFIX_SELECTED_FUNDS


def test_autofix_numpy_assertion() -> None:
    frame = _load_score_frame().loc[["A", "B"]]
    weights = EqualWeight().weight(frame)
    assert abs(weights["weight"].sum() - 1.0) < NUMERICAL_TOLERANCE_MEDIUM
    fancy_array = np.array([1.0, 2.0, 3.0])
    assert fancy_array.tolist() == [1.0, 2.0, 3.0]


def test_yaml_round_trip_and_optional_passthrough(tmp_path: Path) -> None:
    payload = {"hello": 2}
    target = tmp_path / "payload.yaml"
    target.write_text(yaml.safe_dump(payload), encoding="utf-8")
    loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert _optional_passthrough(loaded["hello"]) == 2


def test_aggregate_numbers_pipe_separator() -> None:
    assert aggregate_numbers([1, 2, 3]) == EXPECTED_AGGREGATE_OUTPUT
