from __future__ import annotations

import logging

import pandas as pd

import sitecustomize  # noqa: F401
from trend_analysis.script_logging import setup_script_logging
from trend_analysis.selector import RankSelector
from trend_analysis.weighting import EqualWeight
from trend_analysis import constants


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


def test_equal_weight_adds_weight_column_for_non_empty_frame() -> None:
    frame = pd.DataFrame({"score": [10.0, 20.0]}, index=["a", "b"])

    weighted = EqualWeight().weight(frame)

    assert list(weighted["weight"]) == [0.5, 0.5]
    assert weighted["weight"].sum() == 1.0


def test_setup_script_logging_uses_module_file_name() -> None:
    logger = setup_script_logging(module_file="scripts/example_task.py")

    assert logger.name == "example_task"
    assert logger.level == logging.INFO
    assert any(isinstance(handler, logging.StreamHandler) for handler in logger.handlers)

    for handler in list(logger.handlers):
        logger.removeHandler(handler)


def test_setup_script_logging_preserves_custom_name() -> None:
    logger = setup_script_logging(name="custom_logger", module_file="scripts/example_task.py")

    assert logger.name == "custom_logger"

    for handler in list(logger.handlers):
        logger.removeHandler(handler)


def test_setup_script_logging_is_idempotent() -> None:
    logger = setup_script_logging(name="idempotent_logger")
    initial_handlers = list(logger.handlers)

    logger_again = setup_script_logging(name="idempotent_logger")

    assert logger_again.handlers == initial_handlers

    for handler in list(logger.handlers):
        logger.removeHandler(handler)


def test_constants_tolerance_default() -> None:
    assert constants.NUMERICAL_TOLERANCE_MEDIUM == 1e-6
