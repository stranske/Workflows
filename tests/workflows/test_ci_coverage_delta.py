from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import ci_coverage_delta


def _write_coverage_xml(tmp_path: Path, line_rate: float) -> Path:
    xml = f"""
    <coverage line-rate="{line_rate}" branch-rate="0.5" version="6.5" timestamp="0">
      <packages></packages>
    </coverage>
    """.strip()
    path = tmp_path / "coverage.xml"
    path.write_text(xml, encoding="utf-8")
    return path


def test_coverage_delta_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    xml_path = _write_coverage_xml(tmp_path, 0.9)
    out_path = tmp_path / "delta.json"

    monkeypatch.setenv("COVERAGE_XML_PATH", str(xml_path))
    monkeypatch.setenv("OUTPUT_PATH", str(out_path))
    monkeypatch.setenv("BASELINE_COVERAGE", "85")
    monkeypatch.setenv("ALERT_DROP", "2")
    monkeypatch.setenv("FAIL_ON_DROP", "false")

    try:
        exit_code = ci_coverage_delta.main()
    finally:
        for key in [
            "COVERAGE_XML_PATH",
            "OUTPUT_PATH",
            "BASELINE_COVERAGE",
            "ALERT_DROP",
            "FAIL_ON_DROP",
        ]:
            monkeypatch.delenv(key, raising=False)

    assert exit_code == 0
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["status"] == "ok"
    assert data["current"] == pytest.approx(90.0)
    assert data["delta"] == pytest.approx(5.0)


def test_coverage_delta_alert(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    xml_path = _write_coverage_xml(tmp_path, 0.78)
    out_path = tmp_path / "delta.json"

    monkeypatch.setenv("COVERAGE_XML_PATH", str(xml_path))
    monkeypatch.setenv("OUTPUT_PATH", str(out_path))
    monkeypatch.setenv("BASELINE_COVERAGE", "80")
    monkeypatch.setenv("ALERT_DROP", "1")
    monkeypatch.setenv("FAIL_ON_DROP", "false")

    try:
        exit_code = ci_coverage_delta.main()
    finally:
        for key in [
            "COVERAGE_XML_PATH",
            "OUTPUT_PATH",
            "BASELINE_COVERAGE",
            "ALERT_DROP",
            "FAIL_ON_DROP",
        ]:
            monkeypatch.delenv(key, raising=False)

    assert exit_code == 0
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["status"] == "alert"
    assert data["drop"] == pytest.approx(2.0)


def test_coverage_delta_fail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    xml_path = _write_coverage_xml(tmp_path, 0.7)
    out_path = tmp_path / "delta.json"

    monkeypatch.setenv("COVERAGE_XML_PATH", str(xml_path))
    monkeypatch.setenv("OUTPUT_PATH", str(out_path))
    monkeypatch.setenv("BASELINE_COVERAGE", "80")
    monkeypatch.setenv("ALERT_DROP", "5")
    monkeypatch.setenv("FAIL_ON_DROP", "true")

    try:
        exit_code = ci_coverage_delta.main()
    finally:
        for key in [
            "COVERAGE_XML_PATH",
            "OUTPUT_PATH",
            "BASELINE_COVERAGE",
            "ALERT_DROP",
            "FAIL_ON_DROP",
        ]:
            monkeypatch.delenv(key, raising=False)

    assert exit_code == 1
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["status"] == "fail"


def test_coverage_delta_no_baseline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    xml_path = _write_coverage_xml(tmp_path, 0.65)
    out_path = tmp_path / "delta.json"

    monkeypatch.setenv("COVERAGE_XML_PATH", str(xml_path))
    monkeypatch.setenv("OUTPUT_PATH", str(out_path))
    monkeypatch.setenv("BASELINE_COVERAGE", "0")

    try:
        exit_code = ci_coverage_delta.main()
    finally:
        for key in ["COVERAGE_XML_PATH", "OUTPUT_PATH", "BASELINE_COVERAGE"]:
            monkeypatch.delenv(key, raising=False)

    assert exit_code == 0
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["status"] == "no-baseline"
    assert data["drop"] == 0


def test_coverage_delta_missing_xml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    xml_path = tmp_path / "missing.xml"
    out_path = tmp_path / "delta.json"

    monkeypatch.setenv("COVERAGE_XML_PATH", str(xml_path))
    monkeypatch.setenv("OUTPUT_PATH", str(out_path))

    try:
        exit_code = ci_coverage_delta.main()
    finally:
        for key in ["COVERAGE_XML_PATH", "OUTPUT_PATH"]:
            monkeypatch.delenv(key, raising=False)

    assert exit_code == 1
    assert not out_path.exists()


def test_extract_line_rate_requires_attribute(tmp_path: Path) -> None:
    xml_path = tmp_path / "coverage.xml"
    xml_path.write_text("<coverage></coverage>", encoding="utf-8")

    with pytest.raises(SystemExit, match="missing line-rate"):
        ci_coverage_delta._extract_line_rate(xml_path)


def test_build_payload_ok_when_drop_below_threshold() -> None:
    payload, should_fail = ci_coverage_delta._build_payload(
        current=79.5,
        baseline=80.0,
        alert_drop=2.0,
        fail_on_drop=True,
    )

    assert should_fail is False
    assert payload["status"] == "ok"
    assert payload["drop"] == pytest.approx(0.5)
