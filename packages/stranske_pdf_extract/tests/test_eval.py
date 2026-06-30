"""Golden-set eval harness: normalize-then-compare, macro-F1, regression detection."""

from __future__ import annotations

from stranske_pdf_extract.eval import normalize_value, score_against_golden


def test_normalize_value_numbers_and_text():
    assert normalize_value("$1,234.50") == normalize_value("1234.5")
    assert normalize_value("(100)") == normalize_value("-100")
    assert normalize_value("84%") == normalize_value("84")
    assert normalize_value("  Acme   Capital ") == "acme capital"


def test_normalize_value_preserves_large_decimal_precision():
    assert normalize_value("9007199254740992") != normalize_value("9007199254740993")
    assert normalize_value("12345678901234567890.01") != normalize_value("12345678901234567890.02")


def test_score_against_golden_perfect_and_partial():
    golden = [{"nav": "100.0", "ccy": "USD"}, {"nav": "200.0", "ccy": "EUR"}]
    perfect = score_against_golden(golden, golden)
    assert perfect.macro_f1 == 1.0

    preds = [{"nav": "100.00", "ccy": "USD"}, {"nav": "999.0", "ccy": "EUR"}]
    report = score_against_golden(preds, golden)
    nav = next(fs for fs in report.per_field if fs.key == "nav")
    ccy = next(fs for fs in report.per_field if fs.key == "ccy")
    assert ccy.f1 == 1.0  # both currencies correct
    assert nav.f1 < 1.0  # one nav wrong (normalized 100.0==100.00, 999!=200)


def test_regression_detection():
    golden = [{"nav": "100.0"}]
    baseline = score_against_golden([{"nav": "100.0"}], golden)
    worse = score_against_golden([{"nav": "0"}], golden)
    assert "nav" in worse.regressed_against(baseline)
    assert baseline.regressed_against(baseline) == ()
