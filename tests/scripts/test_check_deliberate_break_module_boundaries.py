"""Probe the selected runtime without turning another module into pytest."""

import json
import runpy
import sys
from pathlib import Path

import pytest


@pytest.fixture(params=["", "templates/consumer-repo/"], ids=["root", "template"])
def helper(request):
    root = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(root / request.param / "scripts/check_deliberate_break.py"))


def test_uv_option_terminator_keeps_the_selected_python_runtime(tmp_path, helper):
    calls = tmp_path / "calls.jsonl"
    imported = tmp_path / "yaml-imported"
    (tmp_path / "yaml.py").write_text(
        f"from pathlib import Path\nPath({str(imported)!r}).write_text('selected-runtime')\n",
        encoding="utf-8",
    )
    uv = tmp_path / "uv"
    uv.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\nfrom pathlib import Path\n"
        f"with Path({str(calls)!r}).open('a') as stream:\n"
        "    stream.write(json.dumps({'args': sys.argv[1:], 'cwd': str(Path.cwd())}) + '\\n')\n"
        "assert sys.argv[1:4] == ['run', '--', 'python']\n"
        "assert sys.argv[4] == '-c', 'must probe, not execute pytest'\n"
        f"os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[4:]])\n",
        encoding="utf-8",
    )
    uv.chmod(0o755)
    command = (str(uv), "run", "--", "python", "-m", "pytest", "-q")

    assert helper["_is_pytest_command"](command) is True
    assert helper["_pyyaml_probe_succeeds"](command, tmp_path) is True
    assert imported.read_text() == "selected-runtime"
    assert [json.loads(line) for line in calls.read_text().splitlines()] == [
        {
            "args": ["run", "--", "python", "-c", helper["PYYAML_PROBE_CODE"]],
            "cwd": str(tmp_path),
        }
    ]


def test_uv_module_named_python_is_not_a_nested_interpreter(tmp_path, monkeypatch, helper):
    command = ("uv", "run", "--module", "python", "-m", "pytest")

    def forbidden_run(*args, **kwargs):
        pytest.fail("a module operand must not cause a runtime probe or package repair")

    monkeypatch.setitem(helper["_run"].__globals__, "_run", forbidden_run)
    assert helper["_is_pytest_command"](command) is False
    assert helper["_pyyaml_probe_command"](command, tmp_path) is None
    assert helper["_pyyaml_probe_succeeds"](command, tmp_path) is False


def test_python_nonpytest_module_does_not_consume_trailing_pytest(tmp_path, monkeypatch, helper):
    command = (sys.executable, "-m", "compileall", "-m", "pytest")

    def forbidden_run(*args, **kwargs):
        pytest.fail("compileall arguments must not turn into a pytest runtime probe")

    monkeypatch.setitem(helper["_run"].__globals__, "_run", forbidden_run)
    assert helper["_is_pytest_command"](command) is False
    assert helper["_pyyaml_probe_command"](command, tmp_path) is None
    assert helper["_pyyaml_probe_succeeds"](command, tmp_path) is False
