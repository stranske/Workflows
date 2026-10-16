"""Execute the actual reusable-workflow receipts on small real pytest runs."""

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml
from scripts.ci_test_growth import junit_report

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_STEP = "Pytest (unit tests with coverage)"
PLUGIN_OPENER = "cat > \"${growth_plugin_dir}/ci_test_growth.py\" <<'PY'"
SUMMARY_STEP = "Record CI summary"
SUMMARY_OPENER = "python - <<'PY'"


def _steps():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/reusable-10-ci-python.yml").read_text(encoding="utf-8")
    )
    return {step["name"]: step for step in workflow["jobs"]["tests"]["steps"]}


def _python_heredoc(script, opener, step_name):
    lines = script.splitlines()
    assert opener in lines, f"{step_name}: missing Python heredoc opener: {opener}"
    start = lines.index(opener) + 1
    assert "PY" in lines[start:], f"{step_name}: missing Python heredoc closing delimiter: PY"
    end = lines.index("PY", start)
    return "\n".join(lines[start:end])


@pytest.mark.parametrize(
    ("step_name", "opener"),
    [(PLUGIN_STEP, PLUGIN_OPENER), (SUMMARY_STEP, SUMMARY_OPENER)],
    ids=["collection-plugin", "ci-summary"],
)
@pytest.mark.parametrize("missing", ["opener", "closing delimiter"])
def test_python_heredoc_missing_delimiter_has_step_diagnostic(step_name, opener, missing):
    script = f"{opener}\nprint('receipt')\nPY\n"
    if missing == "opener":
        script = script.replace(opener, "# opener removed")
    else:
        script = script.replace("\nPY\n", "\nPYTHON\n")
    with pytest.raises(AssertionError) as error:
        _python_heredoc(script, opener, step_name)
    assert step_name in str(error.value)
    assert f"missing Python heredoc {missing}" in str(error.value)


def test_python_heredoc_uses_complete_delimiter_lines():
    script = (
        "PY\n"  # A delimiter before the opener cannot close this heredoc.
        f"{SUMMARY_OPENER}\n"
        "value = '''first\nPYTHON\nlast'''\n"
        "PY\n"
        "echo 'outside Python'\n"
        f"{SUMMARY_OPENER}\nprint('another heredoc')\nPY\n"
    )
    assert _python_heredoc(script, SUMMARY_OPENER, SUMMARY_STEP) == (
        "value = '''first\nPYTHON\nlast'''"
    )


@pytest.mark.parametrize("workers", [0, 2])
def test_selected_collection_receipt_matches_real_pytest(tmp_path, workers):
    script = _steps()[PLUGIN_STEP]["run"]
    plugin = _python_heredoc(script, PLUGIN_OPENER, PLUGIN_STEP)
    (tmp_path / "ci_test_growth.py").write_text(plugin, encoding="utf-8")
    (tmp_path / "test_cases.py").write_text(
        "import pytest\n"
        "@pytest.mark.parametrize('value', [1, 2, 3])\n"
        "def test_selected(value): assert value > 0\n"
        "def test_deselected(): assert False\n",
        encoding="utf-8",
    )
    env = {**os.environ, "PYTHONPATH": str(tmp_path), "PYTEST_ADDOPTS": ""}
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "ci_test_growth",
        "-k",
        "selected and not deselected",
    ]
    if workers:
        command.extend(["-n", str(workers), "--dist=loadgroup"])
    result = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads((tmp_path / "pytest-collection.json").read_text())
    assert receipt["total"] == 3
    assert receipt["per_file"] == {"test_cases.py": 3}
    assert receipt["largest_functions"] == [["test_cases.py::test_selected", 3]]
    assert receipt["collection_seconds"] >= 0


def test_actual_ci_summary_reports_growth_and_preserves_failed_gate(tmp_path):
    script = _python_heredoc(_steps()[SUMMARY_STEP]["run"], SUMMARY_OPENER, SUMMARY_STEP)
    runtime = tmp_path / "artifacts/coverage/runtimes/3.12"
    runtime.mkdir(parents=True)
    (runtime / "pytest-junit.xml").write_text(
        '<testsuites><testsuite><testcase classname="tests.example" name="test_matrix[1]" time="2"/>'
        '<testcase classname="tests.example" name="test_matrix[2]" time="3">'
        '<failure message="real failure"/></testcase></testsuite></testsuites>'
    )
    (tmp_path / "pytest-collection.json").write_text(
        json.dumps(
            {
                "total": 1001,
                "per_file": {"tests/example.py": 1001},
                "largest_functions": [["tests/example.py::test_matrix", 1001]],
            }
        )
    )
    env = {
        **os.environ,
        "PYTHON_VERSION": "3.12",
        "PYTEST_OUTCOME": "failure",
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "job-summary"),
    }
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads((runtime / "summary.json").read_text())
    assert summary["checks"]["tests"]["outcome"] == "failure"
    growth = summary["test_growth"]
    assert growth["collection"]["total"] == 1001
    assert growth["reported"]["cases"] == 2
    assert growth["reported"]["dominant_functions_worker_seconds"] == [
        ["tests.example::test_matrix", 5.0]
    ]
    assert growth["review_required"] is True
    assert (runtime / "pytest-collection.json").exists()
    assert "summed worker time, not wall time" in (tmp_path / "job-summary").read_text()


def test_unreadable_receipts_remain_unknown(tmp_path):
    script = _python_heredoc(_steps()[SUMMARY_STEP]["run"], SUMMARY_OPENER, SUMMARY_STEP)
    runtime = tmp_path / "artifacts/coverage/runtimes/3.12"
    runtime.mkdir(parents=True)
    (runtime / "pytest-junit.xml").write_text("<broken")
    (tmp_path / "pytest-collection.json").write_text("{broken")
    env = {
        **os.environ,
        "PYTHON_VERSION": "3.12",
        "PYTEST_OUTCOME": "failure",
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "job-summary"),
    }
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads((runtime / "summary.json").read_text())
    assert summary["checks"]["tests"]["outcome"] == "failure"
    assert summary["test_growth"]["collection"] is None
    assert summary["test_growth"]["reported"] is None
    assert "collection_error" in summary["test_growth"]
    assert "junit_error" in summary["test_growth"]


@pytest.mark.parametrize("duration", [None, "", "invalid", "NaN", "inf", "-inf", "-1"])
def test_junit_report_preserves_counts_with_unknown_durations(tmp_path, duration):
    path = tmp_path / "junit.xml"
    suite = ET.Element("testsuite")
    for name, seconds in [("test_matrix[1]", duration), ("test_matrix[2]", "2")]:
        case = ET.SubElement(suite, "testcase", classname="tests.example", name=name)
        if seconds is not None:
            case.set("time", seconds)
    ET.SubElement(case, "failure", message="real failure")
    ET.ElementTree(suite).write(path)

    report = junit_report(path)

    assert report["cases"] == 2
    assert report["timed_cases"] == 1
    assert report["untimed_cases"] == 1
    assert report["timing_status"] == "UNKNOWN"
    assert "UNKNOWN" in report["timing_error"]
    assert report["dominant_functions_worker_seconds"] is None
    assert report["dominant_suites_worker_seconds"] is None
    # Receipts must be strict JSON; NaN and infinity are not duration measurements.
    json.dumps(report, allow_nan=False)


def test_junit_report_retains_measured_zero_and_aggregates_parametrizations(tmp_path):
    path = tmp_path / "junit.xml"
    path.write_text(
        '<testsuites><testsuite><testcase classname="tests.example" name="test_zero" time="0"/>'
        '<testcase classname="tests.example" name="test_matrix[1]" time="2"/>'
        '<testcase classname="tests.example" name="test_matrix[2]" time="3"/>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )

    report = junit_report(path)

    assert report["cases"] == report["timed_cases"] == 3
    assert report["untimed_cases"] == 0
    assert report["timing_status"] == "KNOWN"
    assert "timing_error" not in report
    assert report["dominant_functions_worker_seconds"] == [
        ("tests.example::test_matrix", 5.0),
        ("tests.example::test_zero", 0.0),
    ]
    assert report["dominant_suites_worker_seconds"] == [("tests.example", 5.0)]


@pytest.mark.parametrize(
    "cases",
    [
        "",
        '<testcase classname="tests.example" name="test_matrix[1]" time="1e308"/>'
        '<testcase classname="tests.example" name="test_matrix[2]" time="1e308"/>',
    ],
    ids=["no-measurements", "sum-overflow"],
)
def test_junit_report_does_not_publish_unmeasured_or_nonfinite_rankings(tmp_path, cases):
    path = tmp_path / "junit.xml"
    path.write_text(f"<testsuite>{cases}</testsuite>", encoding="utf-8")

    report = junit_report(path)

    assert report["cases"] == (2 if cases else 0)
    assert report["timing_status"] == "UNKNOWN"
    assert report["dominant_functions_worker_seconds"] is None
    assert report["dominant_suites_worker_seconds"] is None
    json.dumps(report, allow_nan=False)


def test_junit_report_propagates_unreadable_xml_to_summary_unknown_handler(tmp_path):
    path = tmp_path / "junit.xml"
    with pytest.raises(FileNotFoundError):
        junit_report(path)
    path.write_text("<broken", encoding="utf-8")
    with pytest.raises(ET.ParseError):
        junit_report(path)
