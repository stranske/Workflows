import json
from pathlib import Path

from scripts import generate_residual_trend


def test_coerce_int_handles_varied_inputs() -> None:
    assert generate_residual_trend._coerce_int(True) == 1
    assert generate_residual_trend._coerce_int(False) == 0
    assert generate_residual_trend._coerce_int(12.7) == 12
    assert generate_residual_trend._coerce_int(" 4 ") == 4
    assert generate_residual_trend._coerce_int("nope") == 0
    assert generate_residual_trend._coerce_int(object()) == 0


def test_sparkline_handles_empty_and_constant_series() -> None:
    assert generate_residual_trend.sparkline([]) == ""
    assert generate_residual_trend.sparkline([3, 3, 3]) == (
        generate_residual_trend.SPARK_CHARS[0] * 3
    )


def test_main_writes_trend_file(tmp_path: Path, monkeypatch) -> None:
    history_path = tmp_path / "history.json"
    out_path = tmp_path / "trend.json"

    history = [
        {"remaining": "5", "new": 1, "by_code": {"F401": 2, "E501": 1}},
        {"remaining": 3, "new": 0, "by_code": {"F401": 1, "E501": 0}},
    ]
    history_path.write_text(json.dumps(history), encoding="utf-8")

    monkeypatch.setattr(generate_residual_trend, "HISTORY", history_path)
    monkeypatch.setattr(generate_residual_trend, "OUT", out_path)

    exit_code = generate_residual_trend.main()

    assert exit_code == 0
    trend = json.loads(out_path.read_text(encoding="utf-8"))
    assert trend["points"] == 2
    assert trend["remaining_latest"] == 3
    assert trend["new_latest"] == 0
    assert len(trend["remaining_spark"]) == 2
    assert len(trend["new_spark"]) == 2
    assert "F401" in trend["codes"]
