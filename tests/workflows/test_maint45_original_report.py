import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

import pytest
import yaml
from scripts.classify_test_failures import _extract_markers, classify_reports

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/maint-45-cosmetic-repair.yml"
TARGET = "baseline[approved].py"


def _run_junit(cwd: Path, report: Path, *selectors: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-o",
            "junit_family=xunit1",
            f"--junitxml={report}",
            *selectors,
        ],
        cwd=cwd,
        env=os.environ | {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        timeout=60,
    )


def test_original_junit_preserves_real_repository_cosmetic_marks(tmp_path: Path) -> None:
    report = tmp_path / "pytest-report.xml"
    result = _run_junit(
        ROOT,
        report,
        "tests/workflows/test_autofix_pr_comment.py::test_load_json_and_coercion_helpers",
        "tests/workflows/test_workflow_multi_failure_demo.py::test_cosmetic_failure",
        "tests/workflows/test_workflow_multi_failure_demo.py::test_lint_failure",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert {
        case.get("name"): _extract_markers(case)
        for case in ElementTree.parse(report).iter("testcase")
    } == {
        "test_load_json_and_coercion_helpers": {"cosmetic"},
        "test_cosmetic_failure": {"cosmetic"},
        "test_lint_failure": set(),
    }


def test_runtime_markers_and_properties_override_cosmetic_decorators(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    for name in ("__init__.py", "conftest.py", "_autofix_diag.py"):
        shutil.copyfile(ROOT / "tests" / name, tests / name)
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\naddopts = --strict-markers\nmarkers =\n    cosmetic\n    runtime\n",
        encoding="utf-8",
    )
    (tests / "test_precedence.py").write_text(
        """import pytest

@pytest.mark.cosmetic
@pytest.mark.runtime
def test_both_decorators():
    pytest.fail('runtime failure')

@pytest.mark.cosmetic
@pytest.mark.parametrize(('key', 'value'), [('test_markers', 'runtime'), ('marker:runtime', 'true')])
def test_explicit_runtime_property(record_property, key, value):
    record_property(key, value)
    pytest.fail('runtime failure')
""",
        encoding="utf-8",
    )
    report = tmp_path / "pytest-report.xml"
    result = _run_junit(tmp_path, report, "tests/test_precedence.py")
    assert result.returncode == 1, result.stdout + result.stderr
    summary = classify_reports([report], reject_repeated_failures=True)
    assert len(summary["runtime"]) == 3
    assert all(record["markers"] == ("cosmetic", "runtime") for record in summary["runtime"])
    assert not summary["cosmetic"] and not summary["unknown"] and not summary["only_cosmetic"]


@pytest.mark.parametrize(
    ("case", "dry_run", "expected_status", "eligible"),
    [
        ("clean", False, "clean", False),
        ("cosmetic", True, "dry-run", False),
        ("cosmetic", False, "applied-no-pr", True),
        ("cosmetic-local", False, "applied-no-pr", True),
        ("already-applied", False, "no-changes", False),
        ("missing-guard", True, None, False),
        ("partial-cosmetic", False, None, False),
        ("duplicate-id", False, None, False),
        ("duplicate-id-local", False, None, False),
        ("ordinary", False, None, False),
        ("mixed", False, None, False),
        ("missing", False, None, False),
        ("empty", False, None, False),
        ("malformed", False, None, False),
        ("no-cases", False, None, False),
        ("inconsistent", False, None, False),
    ],
)
def test_maint45_uses_original_report(tmp_path, case, dry_run, expected_status, eligible):
    local = case.endswith("-local")
    case = case.removesuffix("-local")
    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["repair"]
    steps = {step["name"]: step for step in job["steps"]}
    assert job["env"]["BASE_BRANCH"] == "${{ inputs['base-branch'] }}"
    assert steps["Checkout"]["with"]["ref"] == "${{ env.BASE_BRANCH }}"
    publisher = steps["Create cosmetic repair PR"]
    assert publisher["if"] == "steps.repair.outputs.add_paths != ''"
    assert publisher["with"]["base"] == steps["Checkout"]["with"]["ref"]
    assert sum(step.get("uses", "").startswith("peter-evans/") for step in steps.values()) == 1

    checkout = tmp_path / "checkout"
    (checkout / ".venv/bin").mkdir(parents=True)
    launcher = checkout / ".venv/bin/python"
    launcher.write_text(f'#!/bin/bash\nexec {shlex.quote(sys.executable)} "$@"\n')
    launcher.chmod(0o755)
    (checkout / "scripts").mkdir()
    for name in ("ci_cosmetic_repair.py", "classify_test_failures.py"):
        shutil.copyfile(ROOT / "scripts" / name, checkout / "scripts" / name)
    target = checkout / TARGET
    initial = "1.23456" if case == "already-applied" else "1.23450"
    guard = "" if case == "missing-guard" else "  # cosmetic-repair: float EXPECTED"
    target.write_text(f"EXPECTED = {initial}{guard}\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "selected-base"], cwd=checkout, check=True)
    subprocess.run(["git", "add", "--", TARGET], cwd=checkout, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "base",
        ],
        cwd=checkout,
        check=True,
    )
    report = (checkout if local else tmp_path) / "pytest-report.xml"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update(
        PYTHONDONTWRITEBYTECODE="1",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        RUNNER_TEMP=str(report.parent),
    )
    if case == "cosmetic":
        shutil.copy2(launcher, checkout / ".venv/bin/python3")
        outer_bin = tmp_path / "outer-bin"
        outer_bin.mkdir()
        outer_python = outer_bin / "python3"
        outer_python.write_text("#!/bin/bash\nexit 125\n")
        outer_python.chmod(0o755)
        (checkout / "pytest.ini").write_text("[pytest]\nfilterwarnings = error\n")
        message = "COSMETIC_TOLERANCE " + json.dumps(
            {"path": TARGET, "guard": "float", "key": "EXPECTED", "value": "1.23456"}
        )
        (checkout / "test_cosmetic.py").write_text(
            "import subprocess\n"
            "def test_guarded_drift(record_property):\n"
            "    subprocess.run(['python3', '-c', 'pass'], check=True)\n"
            "    record_property('markers', 'cosmetic')\n"
            f"    assert False, {message!r}\n"
        )
        pytest_outputs = tmp_path / "pytest-outputs"
        subprocess.run(
            ["bash", "-eo", "pipefail", "-c", steps["Run pytest (allow failures)"]["run"]],
            cwd=checkout,
            env={
                **env,
                "PATH": f"{outer_bin}{os.pathsep}{env['PATH']}",
                "GITHUB_OUTPUT": str(pytest_outputs),
            },
            check=True,
            capture_output=True,
        )
        assert pytest_outputs.read_text().strip() == "exit_code=1"
        assert ElementTree.parse(report).find(".//testcase/failure") is not None
    elif case in {"empty", "malformed", "no-cases"}:
        report.write_text({"empty": "", "malformed": "<bad", "no-cases": "<testsuite/>"}[case])
    elif case != "missing":
        suite = ElementTree.Element("testsuite")
        test = ElementTree.SubElement(suite, "testcase", name="original")
        if case in {
            "already-applied",
            "mixed",
            "missing-guard",
            "partial-cosmetic",
            "duplicate-id",
        }:
            properties = ElementTree.SubElement(test, "properties")
            ElementTree.SubElement(properties, "property", name="markers", value="cosmetic")
            instruction = {"path": TARGET, "guard": "float", "key": "EXPECTED", "value": "1.23456"}
            ElementTree.SubElement(test, "failure").text = "COSMETIC_TOLERANCE " + json.dumps(
                instruction
            )
        if case in {"ordinary", "mixed", "duplicate-id"}:
            name = "original" if case == "duplicate-id" else "ordinary"
            ordinary = ElementTree.SubElement(suite, "testcase", name=name)
            ElementTree.SubElement(ordinary, "failure").text = "Runtime regression"
        if case == "partial-cosmetic":
            missing = ElementTree.SubElement(suite, "testcase", name="missing-instruction")
            properties = ElementTree.SubElement(missing, "properties")
            ElementTree.SubElement(properties, "property", name="markers", value="cosmetic")
            ElementTree.SubElement(missing, "failure").text = "No repair instructions"
        ElementTree.ElementTree(suite).write(report)

    original = report.read_bytes() if report.exists() else None
    output = tmp_path / "outputs"
    if local:
        command = [
            sys.executable,
            "-m",
            "scripts.ci_cosmetic_repair",
            "--apply",
            "--skip-pr",
            "--require-all",
            "--report",
            report.name,
        ]
    else:
        command = [
            "bash",
            "-eo",
            "pipefail",
            "-c",
            steps["Run cosmetic repair on original report"]["run"],
        ]
    result = subprocess.run(
        command,
        cwd=checkout,
        env={
            **env,
            "GITHUB_OUTPUT": str(output),
            "PYTEST_EXIT_CODE": "0" if case == "clean" else "1",
            "DRY_RUN": str(dry_run).lower(),
            "BASE_BRANCH": "selected-base",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert (report.read_bytes() if report.exists() else None) == original
    assert not (checkout / ".pytest-cosmetic-report.xml").exists()
    assert (result.returncode == 0) == (
        eligible or expected_status in {"clean", "dry-run"}
    ), result.stderr
    summary = checkout / ".cosmetic-repair-summary.json"
    assert (
        json.loads(summary.read_text())["status"] if summary.exists() else None
    ) == expected_status
    assert output.exists() == (eligible and not local)
    assert ("1.23456" in target.read_text()) == (eligible or case == "already-applied")
    if case == "duplicate-id":
        assert "Repeated failed testcase in the original pytest report" in result.stderr
    if eligible and not local:
        other = checkout / "baselinea.py"
        other.write_text("Do not stage this unrelated path.\n", encoding="utf-8")
        (pathspec,) = output.read_text().splitlines()[1:-1]
        subprocess.run(["git", "add", "--", pathspec], cwd=checkout, check=True)
        names = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"], cwd=checkout, text=True
        )
        assert names.splitlines() == [TARGET]
