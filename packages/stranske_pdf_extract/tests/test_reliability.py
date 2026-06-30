"""Reliability layer: arithmetic checks, cross-check, calibration + routing."""

from __future__ import annotations

from datetime import date

import pytest
from stranske_pdf_extract.reliability import (
    check_date_in_period,
    check_foots,
    check_sign,
    check_weights_sum_to_one,
    cross_check,
    expected_calibration_error,
    route_by_confidence,
)


def test_check_foots_passes_and_fails():
    assert check_foots(line_items=[10.0, 20.0, 70.0], total=100.0) is None
    v = check_foots(line_items=[10.0, 20.0, 69.0], total=100.0, evidence_ref="doc1#page=3")
    assert v is not None and v.rule == "foot_total" and v.evidence_ref == "doc1#page=3"


def test_check_weights_sum():
    assert check_weights_sum_to_one(weights=[0.5, 0.3, 0.2]) is None
    assert check_weights_sum_to_one(weights=[0.5, 0.3, 0.1]) is not None


def test_check_date_in_period_and_sign():
    start, end = date(2026, 1, 1), date(2026, 3, 31)
    assert check_date_in_period(value=date(2026, 2, 15), period_start=start, period_end=end) is None
    assert (
        check_date_in_period(value=date(2026, 4, 1), period_start=start, period_end=end) is not None
    )
    assert check_sign(value=5.0, expected="non_negative") is None
    assert check_sign(value=-5.0, expected="non_negative") is not None
    with pytest.raises(ValueError, match="expected must"):
        check_sign(value=5.0, expected="positive")  # type: ignore[arg-type]


def test_cross_check_flags_specific_fields():
    a = {"nav": "100.0", "ccy": "USD", "manager": "Acme"}
    b = {"nav": "100.00", "ccy": "EUR", "aum": "5B"}
    result = cross_check(a, b)
    assert "nav" in result.agreed  # 100.0 vs 100.00 normalize-equal
    assert "ccy" in result.disagreed
    assert "manager" in result.only_in_a
    assert "aum" in result.only_in_b
    assert set(result.needs_review) == {"ccy", "manager", "aum"}


def test_expected_calibration_error():
    # Perfectly calibrated: confidence == accuracy in each bin -> ECE 0.
    perfect = [(1.0, True), (1.0, True), (0.0, False)]
    assert expected_calibration_error(perfect) == pytest.approx(0.0, abs=1e-9)
    # Overconfident: high confidence, all wrong -> large ECE.
    overconfident = [(0.99, False), (0.98, False)]
    assert expected_calibration_error(overconfident) > 0.9
    assert expected_calibration_error([]) == 0.0
    with pytest.raises(ValueError, match="n_bins"):
        expected_calibration_error([(0.5, True)], n_bins=0)
    with pytest.raises(ValueError, match="confidence"):
        expected_calibration_error([(1.5, True)])


def test_route_by_confidence_double_threshold():
    assert route_by_confidence(0.99) == "auto_accept"
    assert route_by_confidence(0.80) == "human_review"
    assert route_by_confidence(0.10) == "auto_reject"
    with pytest.raises(ValueError):
        route_by_confidence(1.5)
    with pytest.raises(ValueError):
        route_by_confidence(0.9, accept_at=0.5, reject_below=0.8)
