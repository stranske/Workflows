import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from scripts import ci_metrics


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


def test_tag_name_strips_namespace() -> None:
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
