"""Exercise the evidence CLIs across interpreter and report-path boundaries."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-3743/uv-resolution"


@pytest.mark.parametrize(
    "code,case",
    [
        (0, '<testcase name="target"><failure/></testcase>'),
        (1, '<testcase name="target"><error/></testcase>'),
        (1, '<testcase name="target"><failure/><skipped/></testcase>'),
        (1, '<testcase name="wrong"><failure/></testcase>'),
        (1, '<testcase name="target"/>'),
        (1, '<testcase name="target"><failure/></testcase>' * 2),
    ],
    ids=["exit", "error", "skip", "identity", "missing-failure", "case-count"],
)
def test_optimized_replay_rejects_invalid_proof(tmp_path, code, case):
    # A child interpreter is essential: -O must affect the production module.
    program = """
import importlib.util, pathlib, sys, types
# Only fixed synthetic XML is parsed in this proof-validation unit fixture.
# The real replay keeps defusedxml; this stand-in lets -S prove that the
# subprocess validation controls need no undeclared site-package dependency.
from xml.etree import ElementTree
sys.modules['defusedxml'] = types.SimpleNamespace(ElementTree=ElementTree)
spec = importlib.util.spec_from_file_location('replay', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
output = pathlib.Path(sys.argv[2])
def fake_run(argv, **kwargs):
    (output / 'red.xml').write_text('<testsuite>' + sys.argv[4] + '</testsuite>')
    return types.SimpleNamespace(returncode=int(sys.argv[3]))
module.subprocess.run = fake_run
try:
    module.run_case(output, output, 'test_proof.py::target', 'red')
except ValueError:
    print('rejected invalid proof')
else:
    raise SystemExit('accepted invalid proof under optimization')
"""
    result = subprocess.run(
        [
            sys.executable,
            "-O",
            "-S",
            "-c",
            program,
            str(EVIDENCE / "replay_uv_resolution.py"),
            str(tmp_path),
            str(code),
            case,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "rejected invalid proof" in result.stdout
    assert not (tmp_path / "red.json").exists()


def test_replay_suite_cli_quotes_report_paths_with_spaces(tmp_path):
    modules = tmp_path / "fake modules"
    modules.mkdir()
    # This stand-in checks only the CLI transport, not pytest or test outcomes.
    (modules / "pytest.py").write_text(
        """
import json, os, pathlib, shlex, sys
options = shlex.split(os.environ['PYTEST_ADDOPTS'])
if len(options) != 3 or options[2] != '--cov-report=term-missing':
    raise SystemExit('report options split at a space')
coverage = pathlib.Path(options[0].removeprefix('--cov-report=json:'))
junit = pathlib.Path(options[1].removeprefix('--junitxml='))
coverage.write_text(json.dumps({'argv': sys.argv, 'cwd': os.getcwd(),
                              'coverage_file': os.environ['COVERAGE_FILE']}))
junit.write_text('<testsuite/>')
""",
        encoding="utf-8",
    )
    output = tmp_path / "proof reports with spaces"
    env = {**os.environ, "PYTHONPATH": str(modules)}
    result = subprocess.run(
        [sys.executable, str(EVIDENCE / "replay_suites.py"), "--output", str(output)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for phase in ("baseline", "candidate"):
        report = json.loads((output / f"{phase}.json").read_text())
        assert report["cwd"] == str(ROOT)
        assert report["coverage_file"] == str(output / f".coverage-{phase}")
        assert all(str(output) not in arg for arg in report["argv"])
        assert report["argv"][report["argv"].index("-m", 3) + 1] == "not slow"
        assert (output / f"{phase}.xml").read_text() == "<testsuite/>"
        assert json.loads((output / f"{phase}-exit.json").read_text()) == {"exit": 0}
        command = json.loads((output / f"{phase}-command.json").read_text())
        assert command["argv"][0] == sys.executable
        assert command["env"]["COVERAGE_FILE"] == report["coverage_file"]
