"""Runtime-health replay must prove the selected assertion failed and restored."""

import importlib.util
import json
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPLAY = ROOT / "docs/evidence/issue-3743/runtime-health/replay.py"
NODE = "tests/scripts/test_check_deliberate_break_runtime_health.py::test_active_runtime_health_requires_distribution_version_and_real_import[root-missing]"


def report(phase, defect=None, variant="root"):
    failures, errors, skipped = int(phase == "red"), 0, 0
    name = NODE.rsplit("::", 1)[1].replace("[root-", f"[{variant}-")
    module = "tests.scripts.test_check_deliberate_break_runtime_health"
    outcome = '<failure message="assert actual is expected" />' if phase == "red" else ""
    if defect == "error":
        failures, errors, outcome = 0, 1, '<error message="fixture error" />'
    elif defect == "exception":
        outcome = '<failure message="ValueError: execution error" />'
    elif defect == "skip":
        failures, skipped, outcome = 0, 1, "<skipped />"
    elif defect == "wrong-node":
        name = "different_test"
    elif defect == "wrong-module":
        module = "tests.scripts.other"
    elif defect == "inconsistent":
        outcome = "<error />"
    return f'<testsuites><testsuite tests="1" failures="{failures}" errors="{errors}" skipped="{skipped}"><testcase classname="{module}" name="{name}">{outcome}</testcase></testsuite></testsuites>'


def load():
    spec = importlib.util.spec_from_file_location("runtime_health_replay", REPLAY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "defect", [None, "error", "exception", "skip", "wrong-node", "wrong-module", "inconsistent"]
)
def test_main_requires_selected_assertion_outcome_and_restores(tmp_path, monkeypatch, defect):
    module = load()
    module.CASES = module.CASES[:1]
    out = tmp_path / "proof"
    monkeypatch.setattr(sys, "argv", [str(REPLAY), "--output", str(out)])

    def run(argv, **kwargs):
        target = Path(shlex.split(kwargs["env"]["PYTEST_ADDOPTS"])[0].split("=", 1)[1])
        phase = "red" if target.stem.endswith("red") else "green"
        variant = "template" if "[template-" in argv[3] else "root"
        target.write_text(report(phase, defect if phase == "red" else None, variant))
        return SimpleNamespace(returncode=1 if phase == "red" else 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(module.subprocess, "run", run)
    if defect:
        with pytest.raises(RuntimeError):
            module.main()
    else:
        assert module.main() == 0
    rows = json.loads((out / "results.json").read_text())
    assert rows
    assert all(row["original_sha256"] == row["restored_sha256"] for row in rows)


@pytest.mark.parametrize("phase", ["red", "green"])
def test_valid_selected_junit(phase):
    # Filled phase comes from parametrization; no provider or pytest subprocess.
    module = load()
    assert module.validate_junit(report(phase), NODE, phase)["tests"] == 1


def test_optimized_validation_rejects_false_proof():
    code = "import runpy,sys; m=runpy.run_path(sys.argv[1]); m['validate_junit'](sys.argv[2],sys.argv[3],'red')"
    run = subprocess.run(
        [sys.executable, "-O", "-c", code, str(REPLAY), report("red", "error"), NODE],
        capture_output=True,
    )
    assert run.returncode != 0
    assert b"RuntimeError" in run.stderr


@pytest.mark.parametrize(
    "xml",
    [
        '<!DOCTYPE testsuites [<!ENTITY x "boom">]><testsuites>&x;</testsuites>',
        "<bad",
        "",
        '<testsuites><testsuite tests="1" failures="1" errors="0" skipped="0"><failure message="assert x"/><testcase name="x"/></testsuite></testsuites>',
    ],
)
def test_invalid_or_declared_xml_never_admitted(xml):
    with pytest.raises(
        (
            RuntimeError,
            ValueError,
            __import__("xml.parsers.expat", fromlist=["ExpatError"]).ExpatError,
        )
    ):
        load().validate_junit(xml, NODE, "red")
