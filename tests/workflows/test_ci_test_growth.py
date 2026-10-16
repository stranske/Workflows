"""Execute the actual reusable-workflow receipts on small real pytest runs."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _steps():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/reusable-10-ci-python.yml").read_text(encoding="utf-8")
    )
    return {step["name"]: step for step in workflow["jobs"]["tests"]["steps"]}


@pytest.mark.parametrize("workers", [0, 2])
def test_selected_collection_receipt_matches_real_pytest(tmp_path, workers):
    script = _steps()["Pytest (unit tests with coverage)"]["run"]
    assert 'cat > "${growth_plugin_dir}/ci_test_growth.py"' in script
    plugin = script.split("cat > \"${growth_plugin_dir}/ci_test_growth.py\" <<'PY'\n", 1)[1]
    plugin = plugin.split("\nPY\n", 1)[0]
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
    script = _steps()["Record CI summary"]["run"]
    script = script.split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
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
    script = _steps()["Record CI summary"]["run"]
    script = script.split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    runtime = tmp_path / "artifacts/coverage/runtimes/3.12"
    runtime.mkdir(parents=True)
    (runtime / "pytest-junit.xml").write_text("<broken")
    (tmp_path / "pytest-collection.json").write_text("{broken")
    env = {
        **os.environ,
        "PYTHON_VERSION": "3.12",
        "PYTEST_OUTCOME": "failure",
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
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
