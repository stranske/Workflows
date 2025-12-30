from __future__ import annotations

import logging

import pandas as pd

import sitecustomize  # noqa: F401
from trend_analysis.script_logging import setup_script_logging
from trend_analysis.selector import RankSelector
from trend_analysis.weighting import EqualWeight


def test_equal_weight_adds_weight_column_for_empty_frame() -> None:
    frame = pd.DataFrame(columns=["score"])

    weighted = EqualWeight().weight(frame)

    assert weighted.empty
    assert "weight" in weighted.columns


def test_rank_selector_orders_and_splits_frame() -> None:
    frame = pd.DataFrame({"score": [3.0, 1.0, 2.0]}, index=["a", "b", "c"])
    selector = RankSelector(top_n=2, rank_column="score")

    selected, remainder = selector.select(frame)

    assert list(selected.index) == ["a", "c"]
    assert list(remainder.index) == ["b"]


def test_setup_script_logging_uses_module_file_name() -> None:
    logger = setup_script_logging(module_file="scripts/example_task.py")

    assert logger.name == "example_task"
    assert logger.level == logging.INFO
    assert any(isinstance(handler, logging.StreamHandler) for handler in logger.handlers)

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
