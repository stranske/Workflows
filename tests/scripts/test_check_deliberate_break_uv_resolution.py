"""uv executable lookup failures must never produce a runnable probe."""

import json
import runpy
import sys
from pathlib import Path

import pytest


@pytest.fixture(params=["", "templates/consumer-repo/"], ids=["root", "template"])
def helper(request):
    root = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(root / request.param / "scripts/check_deliberate_break.py"))


@pytest.mark.parametrize(
    "phase", ["pytest-nonzero", "pytest-empty", "python-nonzero", "python-empty"]
)
def test_uv_resolution_refuses_failed_or_empty_lookup(tmp_path, helper, phase):
    calls = tmp_path / "calls.jsonl"
    pytest_launcher = tmp_path / "pytest"
    pytest_launcher.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    uv = tmp_path / "uv"
    uv.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\nfrom pathlib import Path\n"
        f"phase = {phase!r}\n"
        f"with Path({str(calls)!r}).open('a') as stream:\n"
        "    stream.write(json.dumps({'args': sys.argv[1:], 'cwd': str(Path.cwd())}) + '\\n')\n"
        "if sys.argv[1:] == ['run', 'which', 'pytest']:\n"
        f"    print('   ' if phase == 'pytest-empty' else {str(pytest_launcher)!r})\n"
        "    raise SystemExit(1 if phase == 'pytest-nonzero' else 0)\n"
        "if sys.argv[1:] == ['run', 'which', 'python3']:\n"
        f"    print('   ' if phase == 'python-empty' else {sys.executable!r})\n"
        "    raise SystemExit(1 if phase == 'python-nonzero' else 0)\n"
        "raise AssertionError('lookup must not launch pytest, Python, or an installer')\n",
        encoding="utf-8",
    )
    uv.chmod(0o755)

    assert helper["_pyyaml_probe_command"]((str(uv), "run", "pytest"), tmp_path) is None

    expected = ["pytest", "python3"] if phase.startswith("python-") else ["pytest"]
    assert [json.loads(line) for line in calls.read_text().splitlines()] == [
        {"args": ["run", "which", name], "cwd": str(tmp_path)} for name in expected
    ]
