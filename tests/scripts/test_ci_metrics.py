import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from scripts import ci_metrics


def _write_junit_xml(path: Path) -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<testsuite>
  <testcase classname="suite" name="test_pass" time="0.4" />
  <testcase classname="suite" name="test_fail" time="1.5">
    <failure message="boom" type="AssertionError">stack</failure>
  </testcase>
  <testcase classname="suite" name="test_error" time="0.7">
    <error message="bad" type="ValueError">trace</error>
  </testcase>
  <testcase classname="suite" name="test_skip" time="0.1">
    <skipped message="skip" type="Skip" />
  </testcase>
</testsuite>
"""
    path.write_text(xml, encoding="utf-8")


def test_parse_helpers_validate_non_negative() -> None:
    assert ci_metrics._parse_int(None, "TOP_N", 5) == 5
    assert ci_metrics._parse_int("", "TOP_N", 5) == 5
    assert ci_metrics._parse_float(None, "MIN_SECONDS", 1.25) == 1.25
    assert ci_metrics._parse_float("", "MIN_SECONDS", 1.25) == 1.25

    with pytest.raises(SystemExit, match="TOP_N must be non-negative"):
        ci_metrics._parse_int("-1", "TOP_N", 5)

    with pytest.raises(SystemExit, match="MIN_SECONDS must be non-negative"):
        ci_metrics._parse_float("-0.5", "MIN_SECONDS", 1.25)


@pytest.mark.parametrize("raw", ["nan", "inf", "-inf"])
def test_parse_float_rejects_non_finite_values(raw: str) -> None:
    with pytest.raises(SystemExit, match="MIN_SECONDS must be finite and non-negative"):
        ci_metrics._parse_float(raw, "MIN_SECONDS", 1.25)


def test_tag_name_strips_namespace() -> None:
    node = ET.Element("{example}testcase")
    assert ci_metrics._tag_name(node) == "testcase"


def test_build_nodeid_handles_missing_values() -> None:
    assert ci_metrics._build_nodeid("suite", "test") == "suite::test"
    assert ci_metrics._build_nodeid("suite", "") == "suite"
    assert ci_metrics._build_nodeid("", "test") == "test"
    assert ci_metrics._build_nodeid("", "") == "(unknown)"


def test_build_metrics_parses_junit(tmp_path: Path) -> None:
    junit_path = tmp_path / "pytest-junit.xml"
    _write_junit_xml(junit_path)

    payload = ci_metrics.build_metrics(junit_path, top_n=2, min_seconds=0.3)

    summary = payload["summary"]
    assert summary == {
        "tests": 4,
        "failures": 1,
        "errors": 1,
        "skipped": 1,
        "passed": 1,
        "duration_seconds": 2.7,
    }

    failures = payload["failures"]
    assert len(failures) == 2
    assert failures[0]["status"] in {"failure", "error"}
    assert failures[0]["message"]

    slow_tests = payload["slow_tests"]
    assert slow_tests["threshold_seconds"] == 0.3
    assert slow_tests["limit"] == 2
    assert len(slow_tests["items"]) == 2
    assert slow_tests["items"][0]["time"] >= slow_tests["items"][1]["time"]


def test_extract_testcases_handles_invalid_time_and_prioritizes_status() -> None:
    xml = """<testsuite>
  <testcase classname="suite" name="bad_time" time="oops">
    <failure message="fail" type="AssertionError"> boom </failure>
    <system-out>ignored</system-out>
  </testcase>
  <testcase classname="suite" name="skipped" time="0.2">
    <skipped />
  </testcase>
</testsuite>
"""
    root = ET.fromstring(xml)

    cases = ci_metrics._extract_testcases(root)

    assert cases[0].time == 0.0
    assert cases[0].outcome == "failure"
    assert cases[0].message == "fail"
    assert cases[0].error_type == "AssertionError"
    assert cases[0].details == "boom"
    assert cases[1].outcome == "skipped"
    assert cases[1].details is None


@pytest.mark.parametrize("duration", ["nan", "inf", "-inf"])
def test_extract_testcases_zeroes_non_finite_durations(duration: str) -> None:
    root = ET.fromstring(
        f'<testsuite><testcase classname="suite" name="case" time="{duration}" /></testsuite>'
    )

    cases = ci_metrics._extract_testcases(root)

    assert cases[0].time == 0.0


def test_collect_slow_tests_handles_zero_limit_and_ties() -> None:
    cases = [
        ci_metrics._TestCase(
            name="a",
            classname="suite",
            nodeid="suite::b",
            time=2.0,
            outcome="passed",
            message=None,
            error_type=None,
            details=None,
        ),
        ci_metrics._TestCase(
            name="b",
            classname="suite",
            nodeid="suite::a",
            time=2.0,
            outcome="passed",
            message=None,
            error_type=None,
            details=None,
        ),
        ci_metrics._TestCase(
            name="c",
            classname="suite",
            nodeid="suite::c",
            time=0.5,
            outcome="passed",
            message=None,
            error_type=None,
            details=None,
        ),
    ]

    assert ci_metrics._collect_slow_tests(cases, top_n=0, min_seconds=0.0) == []

    slow_tests = ci_metrics._collect_slow_tests(cases, top_n=2, min_seconds=1.0)

    assert [entry["nodeid"] for entry in slow_tests] == ["suite::a", "suite::b"]


def _write_sample_junit(tmp_path: Path) -> Path:
    junit_xml = """
    <testsuite name="pytest" tests="4" failures="1" errors="1" skipped="1" time="4.2">
      <testcase classname="pkg.test_mod" name="test_ok" time="0.501" />
      <testcase classname="pkg.test_mod" name="test_fail" time="1.5">
        <failure message="assert false" type="AssertionError">stacktrace here</failure>
      </testcase>
      <testcase classname="pkg.test_mod" name="test_err" time="0.25">
        <error message="boom" type="RuntimeError">traceback</error>
      </testcase>
      <testcase classname="pkg.test_mod" name="test_skip" time="0.0">
        <skipped message="not needed" />
      </testcase>
    </testsuite>
    """.strip()
    junit_path = tmp_path / "pytest-junit.xml"
    junit_path.write_text(junit_xml, encoding="utf-8")
    return junit_path


def test_tag_name_strips_failure_namespace() -> None:
    element = ET.Element("{urn:test}failure")
    assert ci_metrics._tag_name(element) == "failure"


def test_build_nodeid_handles_missing_components() -> None:
    assert ci_metrics._build_nodeid("", "") == "(unknown)"
    assert ci_metrics._build_nodeid("pkg.module", "") == "pkg.module"


def test_parse_float_negative_value_raises() -> None:
    with pytest.raises(SystemExit, match="MIN_SECONDS must be non-negative"):
        ci_metrics._parse_float("-1.5", "MIN_SECONDS", 0.0)


def test_collect_slow_tests_empty_inputs() -> None:
    assert ci_metrics._collect_slow_tests([], top_n=5, min_seconds=0.5) == []

    sample_case = ci_metrics._TestCase(
        name="slow",
        classname="pkg",
        nodeid="pkg::slow",
        time=2.0,
        outcome="passed",
        message=None,
        error_type=None,
        details=None,
    )
    assert ci_metrics._collect_slow_tests([sample_case], top_n=0, min_seconds=0.1) == []


def test_extract_testcases_handles_namespaces_and_invalid_time(tmp_path: Path) -> None:
    junit_xml = """
    <testsuite xmlns:ns="urn:test" tests="1">
      <testcase name="" classname="" time="invalid">
        <system-out>ignored logs</system-out>
        <ns:skipped message="opt-out" type="SkipType"> details </ns:skipped>
      </testcase>
    </testsuite>
    """.strip()
    junit_path = tmp_path / "namespaced.xml"
    junit_path.write_text(junit_xml, encoding="utf-8")

    root = ET.parse(junit_path).getroot()
    [case] = ci_metrics._extract_testcases(root)
    assert case.nodeid == "(unknown)"
    assert case.time == pytest.approx(0.0)
    assert case.outcome == "skipped"
    assert case.message == "opt-out"
    assert case.error_type == "SkipType"
    assert case.details == "details"


def test_build_metrics_extracts_counts_and_failures(tmp_path: Path) -> None:
    junit_path = _write_sample_junit(tmp_path)

    payload = ci_metrics.build_metrics(junit_path, top_n=5, min_seconds=0.2)

    summary = payload["summary"]
    assert summary == {
        "tests": 4,
        "failures": 1,
        "errors": 1,
        "skipped": 1,
        "passed": 1,
        "duration_seconds": pytest.approx(2.251, rel=1e-6),
    }

    failure_entries = payload["failures"]
    assert len(failure_entries) == 2
    assert failure_entries[0] == {
        "status": "failure",
        "name": "test_fail",
        "classname": "pkg.test_mod",
        "nodeid": "pkg.test_mod::test_fail",
        "time": pytest.approx(1.5),
        "message": "assert false",
        "type": "AssertionError",
        "details": "stacktrace here",
    }
    assert failure_entries[1]["status"] == "error"
    assert failure_entries[1]["details"] == "traceback"


def test_build_metrics_slow_tests_filter(tmp_path: Path) -> None:
    junit_path = _write_sample_junit(tmp_path)

    payload = ci_metrics.build_metrics(junit_path, top_n=2, min_seconds=1.0)

    slow = payload["slow_tests"]
    assert slow["threshold_seconds"] == 1.0
    assert slow["limit"] == 2
    assert slow["items"] == [
        {
            "name": "test_fail",
            "classname": "pkg.test_mod",
            "nodeid": "pkg.test_mod::test_fail",
            "time": pytest.approx(1.5),
            "outcome": "failure",
        }
    ]


def test_main_writes_output_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    junit_path = _write_sample_junit(tmp_path)
    out_path = tmp_path / "ci-metrics.json"

    monkeypatch.setenv("JUNIT_PATH", str(junit_path))
    monkeypatch.setenv("OUTPUT_PATH", str(out_path))
    monkeypatch.setenv("TOP_N", "3")
    monkeypatch.setenv("MIN_SECONDS", "0")

    try:
        exit_code = ci_metrics.main()
    finally:
        monkeypatch.delenv("JUNIT_PATH", raising=False)
        monkeypatch.delenv("OUTPUT_PATH", raising=False)
        monkeypatch.delenv("TOP_N", raising=False)
        monkeypatch.delenv("MIN_SECONDS", raising=False)

    assert exit_code == 0
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["summary"]["tests"] == 4
    assert data["slow_tests"]["limit"] == 3


def test_main_missing_junit_returns_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    junit_path = tmp_path / "missing.xml"
    out_path = tmp_path / "unused.json"

    monkeypatch.setenv("JUNIT_PATH", str(junit_path))
    monkeypatch.setenv("OUTPUT_PATH", str(out_path))

    try:
        exit_code = ci_metrics.main()
    finally:
        monkeypatch.delenv("JUNIT_PATH", raising=False)
        monkeypatch.delenv("OUTPUT_PATH", raising=False)

    assert exit_code == 1
    assert not out_path.exists()


def test_invalid_top_n_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    junit_path = _write_sample_junit(tmp_path)
    out_path = tmp_path / "ci-metrics.json"

    monkeypatch.setenv("JUNIT_PATH", str(junit_path))
    monkeypatch.setenv("OUTPUT_PATH", str(out_path))
    monkeypatch.setenv("TOP_N", "-4")

    with pytest.raises(SystemExit):
        ci_metrics.main()

    monkeypatch.delenv("JUNIT_PATH", raising=False)
    monkeypatch.delenv("OUTPUT_PATH", raising=False)
    monkeypatch.delenv("TOP_N", raising=False)
