from pathlib import Path
from xml.etree import ElementTree as ET

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
