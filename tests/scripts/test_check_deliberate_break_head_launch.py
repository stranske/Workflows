"""A real unavailable head command is a broken proof, never an acceptance verdict."""

import errno
import json
import runpy
from pathlib import Path

import pytest


@pytest.fixture(params=["", "templates/consumer-repo/"], ids=["root", "template"])
def helper(request):
    root = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(root / request.param / "scripts/check_deliberate_break.py"))


@pytest.mark.parametrize("failure", ["missing", "not-executable"])
def test_unavailable_head_command_is_reported_without_base_or_repair(
    tmp_path, monkeypatch, helper, failure
):
    proof = tmp_path / "proof.txt"
    proof.write_bytes(b"candidate proof\r\n")
    launcher = tmp_path / "private-command"
    if failure == "not-executable":
        launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        launcher.chmod(0o644)
    command = (str(launcher), "argument with spaces")
    namespace = helper["verify_spec"].__globals__
    original_run = namespace["_run"]
    observed = []

    def run(argv, cwd):
        try:
            return original_run(argv, cwd)
        except OSError as error:
            observed.append((argv, cwd, error))
            raise

    def forbidden(*args):
        pytest.fail("unavailable head must not repair dependencies or extract the base")

    monkeypatch.setitem(namespace, "_run", run)
    monkeypatch.setitem(namespace, "_ensure_pytest_runtime_deps", forbidden)
    monkeypatch.setitem(namespace, "_archive_ref", forbidden)
    spec = helper["DeliberateBreakSpec"]("head-proof", "proof.txt", "app.py", command)
    result = helper["verify_spec"](spec, base="unused", cwd=tmp_path, enforce_tamper=False)

    assert result["verdict"] == "FAIL_BROKEN"
    assert len(observed) == 1
    argv, cwd, error = observed[0]
    assert (argv, cwd) == (command, tmp_path)
    assert type(error) is (FileNotFoundError if failure == "missing" else PermissionError)
    assert error.errno == (errno.ENOENT if failure == "missing" else errno.EACCES)
    assert error.filename == str(launcher)
    assert result == {
        "verdict": "FAIL_BROKEN",
        "reason": "command-unavailable",
        "command": list(command),
        "detail": str(error),
    }
    assert json.loads(json.dumps(result)) == result
    assert proof.read_bytes() == b"candidate proof\r\n"
    assert sorted(path.name for path in tmp_path.iterdir()) == (
        ["proof.txt"] if failure == "missing" else ["private-command", "proof.txt"]
    )
    if launcher.exists():
        assert launcher.read_bytes() == b"#!/bin/sh\nexit 0\n"
        assert launcher.stat().st_mode & 0o777 == 0o644
