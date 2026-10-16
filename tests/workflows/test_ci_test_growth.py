"""Execute the actual reusable-workflow receipts on small real pytest runs."""

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

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


class _PartialCollectionPublished(AssertionError):
    """The workflow presented a failed collection's subset as complete."""


@pytest.mark.parametrize("workers", [0, 2])
def test_serial_collection_error_does_not_publish_complete_receipt(tmp_path, workers):
    plugin = _python_heredoc(_steps()[PLUGIN_STEP]["run"], PLUGIN_OPENER, PLUGIN_STEP)
    (tmp_path / "ci_test_growth.py").write_text(plugin, encoding="utf-8")
    (tmp_path / "test_good.py").write_text(
        "import pytest\n"
        "@pytest.mark.parametrize('value', [1, 2, 3])\n"
        "def test_selected(value): assert value > 0\n",
        encoding="utf-8",
    )
    (tmp_path / "test_broken.py").write_text("def test_broken(:\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "ci_test_growth",
            *(["-n", str(workers)] if workers else []),
            "-q",
            "-m",
            "not slow",
            "test_good.py",
            "test_broken.py",
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path), "PYTEST_ADDOPTS": ""},
        capture_output=True,
        text=True,
    )
    # Infrastructure or fixture failures must fail normally, rather than xfail.
    assert result.returncode in (pytest.ExitCode.INTERRUPTED, pytest.ExitCode.TESTS_FAILED), (
        result.stdout + result.stderr
    )
    assert "test_broken.py" in result.stdout
    assert "SyntaxError" in result.stdout
    receipt_path = tmp_path / "pytest-collection.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert isinstance(receipt, dict)
        if receipt.get("complete") is not False:
            raise _PartialCollectionPublished(
                f"collection exited {result.returncode}, but published a complete-looking "
                f"receipt with {receipt.get('total')} selected cases"
            )


def test_serial_test_failure_preserves_complete_collection_receipt(tmp_path):
    plugin = _python_heredoc(_steps()[PLUGIN_STEP]["run"], PLUGIN_OPENER, PLUGIN_STEP)
    (tmp_path / "ci_test_growth.py").write_text(plugin, encoding="utf-8")
    (tmp_path / "test_cases.py").write_text(
        "import pytest\n"
        "@pytest.mark.parametrize('value', [1, 2, 3])\n"
        "def test_selected(value): assert value != 2\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "ci_test_growth", "-q", "-m", "not slow"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path), "PYTEST_ADDOPTS": ""},
        capture_output=True,
        text=True,
    )
    assert result.returncode == pytest.ExitCode.TESTS_FAILED, result.stdout + result.stderr
    assert "1 failed, 2 passed" in result.stdout
    receipt = json.loads((tmp_path / "pytest-collection.json").read_text(encoding="utf-8"))
    assert receipt["total"] == 3
    assert receipt["per_file"] == {"test_cases.py": 3}
    assert receipt["largest_functions"] == [["test_cases.py::test_selected", 3]]
    assert receipt.get("complete") is not False


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
    from scripts.ci_test_growth import junit_report

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
    from scripts.ci_test_growth import junit_report

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
    from scripts.ci_test_growth import junit_report

    path = tmp_path / "junit.xml"
    path.write_text(f"<testsuite>{cases}</testsuite>", encoding="utf-8")

    report = junit_report(path)

    assert report["cases"] == (2 if cases else 0)
    assert report["timing_status"] == "UNKNOWN"
    assert report["dominant_functions_worker_seconds"] is None
    assert report["dominant_suites_worker_seconds"] is None
    json.dumps(report, allow_nan=False)


def test_junit_report_propagates_unreadable_xml_to_summary_unknown_handler(tmp_path):
    from scripts.ci_test_growth import junit_report

    path = tmp_path / "junit.xml"
    with pytest.raises(FileNotFoundError):
        junit_report(path)
    path.write_text("<broken", encoding="utf-8")
    with pytest.raises(ET.ParseError):
        junit_report(path)


@pytest.mark.parametrize(
    "receipt",
    [
        {"largest_functions": [1]},
        {"per_file": {"a": "x"}},
        [],
        {"largest_functions": [["a", True]]},
        {"total": -1},
    ],
)
def test_actual_summary_rejects_malformed_collection_shape(tmp_path, receipt):
    script = _python_heredoc(_steps()[SUMMARY_STEP]["run"], SUMMARY_OPENER, SUMMARY_STEP)
    (tmp_path / "pytest-collection.json").write_text(json.dumps(receipt))
    env = {**os.environ, "PYTHON_VERSION": "3.12", "GITHUB_OUTPUT": str(tmp_path / "outputs")}
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    growth = json.loads((tmp_path / "artifacts/coverage/runtimes/3.12/summary.json").read_text())[
        "test_growth"
    ]
    assert growth["collection"] is None
    assert "malformed" in growth["collection_error"]


def test_actual_summary_preserves_counts_for_invalid_duration(tmp_path):
    script = _python_heredoc(_steps()[SUMMARY_STEP]["run"], SUMMARY_OPENER, SUMMARY_STEP)
    runtime = tmp_path / "artifacts/coverage/runtimes/3.12"
    runtime.mkdir(parents=True)
    (runtime / "pytest-junit.xml").write_text(
        '<testsuite><testcase name="a" time="invalid"/><testcase name="b" time="2"/></testsuite>'
    )
    env = {**os.environ, "PYTHON_VERSION": "3.12", "GITHUB_OUTPUT": str(tmp_path / "outputs")}
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    growth = json.loads((runtime / "summary.json").read_text())["test_growth"]
    assert growth["reported"]["cases"] == 2
    assert growth["reported"]["timing_status"] == "UNKNOWN"
    assert growth["reported"]["dominant_functions_worker_seconds"] is None


def test_junit_report_rejects_entity_expansion(tmp_path):
    from defusedxml.common import DefusedXmlException
    from scripts.ci_test_growth import junit_report

    path = tmp_path / "junit.xml"
    path.write_text(
        '<!DOCTYPE testsuite [<!ENTITY secret "expanded">]><testsuite><testcase name="&secret;" time="1"/></testsuite>'
    )
    with pytest.raises(DefusedXmlException):
        junit_report(path)


def test_embedded_junit_helper_matches_source_without_consumer_import():
    import ast
    import inspect

    from scripts.ci_test_growth import junit_report

    inline = _python_heredoc(_steps()[SUMMARY_STEP]["run"], SUMMARY_OPENER, SUMMARY_STEP)
    node = next(
        node
        for node in ast.parse(inline).body
        if isinstance(node, ast.FunctionDef) and node.name == "junit_report"
    )
    assert ast.dump(node) == ast.dump(ast.parse(inspect.getsource(junit_report)).body[0])


def test_workflow_clears_stale_receipt_before_pytest_startup_error(tmp_path):
    script = _steps()[PLUGIN_STEP]["run"]
    tail = script[script.index("# Clear stale evidence") :]
    (tmp_path / "pytest-collection.json").write_text('{"total": 9999}')
    env = {
        **os.environ,
        "RUNNER_TEMP": str(tmp_path),
        "PYTEST_ADDOPTS": "",
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
    }
    result = subprocess.run(
        ["bash", "-c", 'args=("missing_test_file.py")\n' + tail],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == pytest.ExitCode.USAGE_ERROR, result.stdout + result.stderr
    assert not (tmp_path / "pytest-collection.json").exists()


def test_actual_summary_refuses_junit_entity_expansion(tmp_path):
    script = _python_heredoc(_steps()[SUMMARY_STEP]["run"], SUMMARY_OPENER, SUMMARY_STEP)
    runtime = tmp_path / "artifacts/coverage/runtimes/3.12"
    runtime.mkdir(parents=True)
    (runtime / "pytest-junit.xml").write_text(
        '<!DOCTYPE testsuite [<!ENTITY secret "expanded">]><testsuite><testcase name="&secret;" time="1"/></testsuite>'
    )
    env = {**os.environ, "PYTHON_VERSION": "3.12", "GITHUB_OUTPUT": str(tmp_path / "outputs")}
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    growth = json.loads((runtime / "summary.json").read_text())["test_growth"]
    assert growth["reported"] is None
    assert "unsafe" in growth["junit_error"]


@pytest.mark.parametrize("workers", [0, 2])
def test_instrumentation_does_not_pollute_product_coverage(tmp_path, workers, monkeypatch):
    """A temporary CI plugin is infrastructure; uncovered product stays enforced."""
    # Hosted selftests enable ambient plugin discovery; the child must isolate it.
    monkeypatch.delenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", raising=False)
    plugin_dir = tmp_path / "instrumentation"
    plugin_dir.mkdir()
    plugin = _python_heredoc(_steps()[PLUGIN_STEP]["run"], PLUGIN_OPENER, PLUGIN_STEP)
    (plugin_dir / "ci_test_growth.py").write_text(plugin, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.coverage.run]\nomit = ["test_product.py"]\n', encoding="utf-8"
    )
    product = tmp_path / "product.py"
    product.write_text("def identity(value):\n    return value\n", encoding="utf-8")
    (tmp_path / "test_product.py").write_text(
        "from product import identity\ndef test_identity(): assert identity(3) == 3\n",
        encoding="utf-8",
    )
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "ci_test_growth",
        "--cov",
        "--cov-config=pyproject.toml",
        "--cov-report=json:coverage.json",
        "--cov-fail-under=70",
        "-q",
        "test_product.py",
        *(["-n", str(workers)] if workers else []),
    ]
    env = {
        **os.environ,
        "PYTHONPATH": str(plugin_dir) + os.pathsep + str(tmp_path),
        "PYTEST_ADDOPTS": "",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTEST_PLUGINS": "xdist.plugin,pytest_cov.plugin",
    }
    result = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / "coverage.json").read_text())
    assert report["totals"]["percent_covered"] == 100
    assert report["files"]["product.py"]["summary"]["num_statements"] == 2
    assert json.loads((tmp_path / "pytest-collection.json").read_text())["total"] == 1

    # The infrastructure exclusion must not hide genuine uncovered product code.
    product.write_text(
        product.read_text()
        + "\ndef uncovered():\n    value = 7\n    value += 1\n    return value\n"
    )
    result = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads((tmp_path / "coverage.json").read_text())
    assert report["totals"]["percent_covered"] == 50
    assert report["files"]["product.py"]["summary"]["missing_lines"] == 3
