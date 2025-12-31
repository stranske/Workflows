import json
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts import classify_test_failures


def _write_junit(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<testsuite>\n'
        f"{body}\n</testsuite>\n",
        encoding="utf-8",
    )
    return path


def test_classify_reports_ignores_missing_file() -> None:
    summary = classify_test_failures.classify_reports(["missing-report.xml"])

    assert summary["total_failures"] == 0
    assert summary["has_failures"] is False
    assert summary["only_cosmetic"] is False
    assert summary["cosmetic"] == []
    assert summary["runtime"] == []
    assert summary["unknown"] == []


def test_classify_reports_handles_parse_error(tmp_path: Path) -> None:
    report = tmp_path / "bad-report.xml"
    report.write_text("<testsuite>", encoding="utf-8")

    summary = classify_test_failures.classify_reports([report])

    assert summary["total_failures"] == 1
    assert summary["has_failures"] is True
    assert summary["unknown"][0]["failure_type"] == "error"
    assert "Unable to parse JUnit XML" in summary["unknown"][0]["message"]
    assert summary["unknown"][0]["id"].startswith("<parse-error>:")


def test_classify_reports_classifies_markers_and_dedupes(tmp_path: Path) -> None:
    body = """
    <testcase classname="pkg.test_mod" name="test_runtime">
      <properties>
        <property name="markers" value="runtime, smoke"/>
      </properties>
      <failure message="boom">trace<detail/></failure>
    </testcase>
    <testcase classname="pkg.test_mod" name="test_runtime">
      <properties>
        <property name="Marker:Runtime" value="1"/>
      </properties>
      <failure message="boom">trace<detail/></failure>
    </testcase>
    <testcase classname="pkg.test_mod" name="test_cosmetic">
      <properties>
        <property name="marker:cosmetic" value="1"/>
      </properties>
      <error>stack</error>
    </testcase>
    <testcase classname="pkg.test_mod" name="test_unknown_marker">
      <properties>
        <property name="markers" value="flaky"/>
      </properties>
      <failure message="nope"><detail/></failure>
    </testcase>
    <testcase classname="pkg.test_mod" name="test_default_runtime">
      <failure message="default"><detail/></failure>
    </testcase>
    """
    report = _write_junit(tmp_path, "report.xml", body)

    summary = classify_test_failures.classify_reports([report])

    assert summary["total_failures"] == 4
    assert summary["has_failures"] is True
    assert len(summary["runtime"]) == 2
    assert len(summary["cosmetic"]) == 1
    assert len(summary["unknown"]) == 1
    assert summary["cosmetic"][0]["failure_type"] == "error"
    assert summary["runtime"][0]["message"].startswith("boom:")


def test_failure_message_and_test_id_helpers() -> None:
    failure_case = ET.fromstring(
        '<testcase classname="pkg.mod" name="test_it">'
        '<failure message="boom">trace</failure>'
        "</testcase>"
    )
    message, failure_type = classify_test_failures._failure_message(failure_case)

    assert failure_type == "failure"
    assert message == "boom: trace"
    assert classify_test_failures._test_id(failure_case, Path("report.xml")) == "pkg.mod::test_it"

    error_case = ET.fromstring("<testcase name=\"test_err\"><error>stack</error></testcase>")
    message, failure_type = classify_test_failures._failure_message(error_case)

    assert failure_type == "error"
    assert message == "stack"
    assert classify_test_failures._test_id(error_case, Path("report.xml")) == "test_err"

    unnamed_case = ET.fromstring("<testcase></testcase>")
    assert (
        classify_test_failures._test_id(unnamed_case, Path("report.xml"))
        == "report.xml::testcase"
    )
    empty_case = ET.fromstring("<testcase></testcase>")
    assert classify_test_failures._failure_message(empty_case) == ("", "failure")


def test_extract_markers_skips_blank_values() -> None:
    testcase = ET.fromstring(
        "<testcase>"
        "<properties>"
        "<property name=\"markers\" value=\"\"/>"
        "<property name=\"marker:runtime\" value=\"1\"/>"
        "<property name=\"note\" value=\"ignored\"/>"
        "</properties>"
        "</testcase>"
    )

    markers = classify_test_failures._extract_markers(testcase)

    assert markers == {"runtime"}


def test_classify_reports_skips_non_failures(tmp_path: Path) -> None:
    report = _write_junit(
        tmp_path,
        "report.xml",
        """
        <testcase classname="pkg.test_mod" name="test_ok"/>
        <testcase classname="pkg.test_mod" name="test_error">
          <error>stack</error>
        </testcase>
        """,
    )

    summary = classify_test_failures.classify_reports([report])

    assert summary["total_failures"] == 1


def test_main_writes_output_file(tmp_path: Path, capsys, monkeypatch) -> None:
    report = _write_junit(
        tmp_path,
        "report.xml",
        """
        <testcase classname="pkg.test_mod" name="test_runtime">
          <failure message="boom"><detail/></failure>
        </testcase>
        """,
    )
    output = tmp_path / "summary.json"

    monkeypatch.chdir(tmp_path)
    status = classify_test_failures.main([report.name, "--output", str(output)])

    assert status == 0
    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["has_failures"] is True
    assert payload["total_failures"] == 1
    assert "cosmetic" in payload

    captured = capsys.readouterr()
    assert '"total_failures": 1' in captured.out


def test_main_with_missing_report_prints_empty_summary(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    status = classify_test_failures.main(["missing-report.xml"])

    assert status == 0
    captured = capsys.readouterr()
    assert '"total_failures": 0' in captured.out
