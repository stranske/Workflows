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
