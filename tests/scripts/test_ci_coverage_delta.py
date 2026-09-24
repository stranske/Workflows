from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts import ci_coverage_delta


def _coverage_xml(tmp_path: Path, *, line_rate: str = "0.81234") -> Path:
    xml_path = tmp_path / "coverage.xml"
    xml_path.write_text(
        f'<coverage line-rate="{line_rate}" branch-rate="0.0"><packages /></coverage>',
        encoding="utf-8",
    )
    return xml_path


@pytest.mark.parametrize("raw", [None, ""])
def test_parse_float_uses_default_for_missing_values(raw: str | None) -> None:
    assert ci_coverage_delta._parse_float(raw, "VALUE", 12.5) == 12.5


def test_parse_float_accepts_valid_values() -> None:
    assert ci_coverage_delta._parse_float("7.25", "VALUE", 0.0) == 7.25


def test_parse_float_rejects_invalid_values() -> None:
    with pytest.raises(SystemExit, match="Invalid float for BASELINE_COVERAGE"):
        ci_coverage_delta._parse_float("not-a-number", "BASELINE_COVERAGE", 0.0)


@pytest.mark.parametrize("raw", ["nan", "inf", "-inf"])
def test_parse_float_rejects_non_finite_values(raw: str) -> None:
    with pytest.raises(SystemExit, match="BASELINE_COVERAGE"):
        ci_coverage_delta._parse_float(raw, "BASELINE_COVERAGE", 0.0)


@pytest.mark.parametrize(
    ("raw", "minimum", "maximum"),
    [("-0.1", 0.0, None), ("100.1", 0.0, 100.0)],
)
def test_parse_float_rejects_out_of_range_values(
    raw: str, minimum: float, maximum: float | None
) -> None:
    with pytest.raises(SystemExit, match="BASELINE_COVERAGE"):
        ci_coverage_delta._parse_float(
            raw,
            "BASELINE_COVERAGE",
            0.0,
            minimum=minimum,
            maximum=maximum,
        )


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on"])
def test_truthy_accepts_enabled_values(raw: str) -> None:
    assert ci_coverage_delta._truthy(raw) is True


@pytest.mark.parametrize("raw", [None, "", "0", "false", "no", "off", "anything-else"])
def test_truthy_rejects_disabled_values(raw: str | None) -> None:
    assert ci_coverage_delta._truthy(raw) is False


def test_extract_line_rate_reads_percentage(tmp_path: Path) -> None:
    assert ci_coverage_delta._extract_line_rate(_coverage_xml(tmp_path)) == pytest.approx(81.234)


def test_extract_line_rate_requires_existing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Coverage XML not found"):
        ci_coverage_delta._extract_line_rate(tmp_path / "missing.xml")


def test_extract_line_rate_rejects_malformed_xml(tmp_path: Path) -> None:
    xml_path = tmp_path / "coverage.xml"
    xml_path.write_text("<coverage", encoding="utf-8")

    with pytest.raises(SystemExit, match="Failed to parse coverage XML"):
        ci_coverage_delta._extract_line_rate(xml_path)


def test_extract_line_rate_rejects_malformed_rate(tmp_path: Path) -> None:
    xml_path = _coverage_xml(tmp_path, line_rate="not-a-float")

    with pytest.raises(SystemExit, match="Invalid line-rate value"):
        ci_coverage_delta._extract_line_rate(xml_path)


@pytest.mark.parametrize("line_rate", ["nan", "inf", "-inf"])
def test_extract_line_rate_rejects_non_finite_rate(tmp_path: Path, line_rate: str) -> None:
    xml_path = _coverage_xml(tmp_path, line_rate=line_rate)

    with pytest.raises(SystemExit, match="finite and between 0 and 1"):
        ci_coverage_delta._extract_line_rate(xml_path)


@pytest.mark.parametrize("line_rate", ["-0.1", "1.1"])
def test_extract_line_rate_rejects_out_of_range_rate(tmp_path: Path, line_rate: str) -> None:
    xml_path = _coverage_xml(tmp_path, line_rate=line_rate)

    with pytest.raises(SystemExit, match="between 0 and 1"):
        ci_coverage_delta._extract_line_rate(xml_path)


@pytest.mark.parametrize(
    ("current", "baseline", "alert_drop", "fail_on_drop", "status", "should_fail"),
    [
        (82.0, 0.0, 1.0, False, "no-baseline", False),
        (82.0, 80.0, 1.0, True, "ok", False),
        (78.5, 80.0, 1.0, False, "alert", False),
        (78.5, 80.0, 1.0, True, "fail", True),
    ],
)
def test_build_payload_status_matrix(
    current: float,
    baseline: float,
    alert_drop: float,
    fail_on_drop: bool,
    status: str,
    should_fail: bool,
) -> None:
    payload, actual_should_fail = ci_coverage_delta._build_payload(
        current=current,
        baseline=baseline,
        alert_drop=alert_drop,
        fail_on_drop=fail_on_drop,
    )

    assert actual_should_fail is should_fail
    assert payload["status"] == status
    assert payload["current"] == pytest.approx(current)
    assert payload["baseline"] == pytest.approx(baseline)
    assert payload["threshold"] == pytest.approx(alert_drop)
    assert payload["fail_on_drop"] is fail_on_drop


def test_main_writes_rounded_payload_from_env_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xml_path = _coverage_xml(tmp_path, line_rate="0.789876")
    output_path = tmp_path / "delta.json"

    monkeypatch.setenv("COVERAGE_XML_PATH", str(xml_path))
    monkeypatch.setenv("OUTPUT_PATH", str(output_path))
    monkeypatch.setenv("BASELINE_COVERAGE", "80")
    monkeypatch.setenv("ALERT_DROP", "2")
    monkeypatch.setenv("FAIL_ON_DROP", "yes")

    assert ci_coverage_delta.main() == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["current"] == pytest.approx(78.9876)
    assert payload["baseline"] == pytest.approx(80.0)
    assert payload["delta"] == pytest.approx(-1.0124)
    assert payload["drop"] == pytest.approx(1.0124)
    assert payload["status"] == "ok"
    assert payload["fail_on_drop"] is True


def test_main_rejects_nan_baseline_without_writing_ok_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xml_path = _coverage_xml(tmp_path, line_rate="0.70")
    output_path = tmp_path / "delta.json"

    monkeypatch.setenv("COVERAGE_XML_PATH", str(xml_path))
    monkeypatch.setenv("OUTPUT_PATH", str(output_path))
    monkeypatch.setenv("BASELINE_COVERAGE", "nan")
    monkeypatch.setenv("FAIL_ON_DROP", "true")

    with pytest.raises(SystemExit, match="BASELINE_COVERAGE"):
        ci_coverage_delta.main()

    assert not output_path.exists()
