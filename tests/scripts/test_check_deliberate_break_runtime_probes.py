"""Keep runtime discovery failures distinct from executed test failures.

The child runtimes here are private files, not package installations. Both
distributed helper copies must preserve the launch error and its original cause.
"""

import errno
import runpy
import sys
from pathlib import Path

import pytest


@pytest.fixture(params=["", "templates/consumer-repo/"], ids=["root", "template"])
def helper(request):
    root = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(root / request.param / "scripts/check_deliberate_break.py"))


@pytest.fixture
def runtime_calls(helper, monkeypatch):
    """Observe the real runner, including the exact OS exception it raises."""
    namespace = helper["_run"].__globals__
    run = namespace["_run"]
    calls = []

    def observed_run(command, cwd):
        call = {"command": command, "cwd": cwd}
        calls.append(call)
        try:
            call["result"] = run(command, cwd)
        except OSError as error:
            call["error"] = error
            raise
        return call["result"]

    monkeypatch.setitem(namespace, "_run", observed_run)
    return calls


@pytest.mark.parametrize("mode", ["healthy", "zero-without-sentinel", "nonzero"])
def test_real_import_probe_requires_success_and_its_sentinel(tmp_path, helper, runtime_calls, mode):
    marker = tmp_path / "imported"
    code = f"from pathlib import Path\nPath({str(marker)!r}).write_text('yaml-import')\n"
    if mode != "healthy":
        if mode == "nonzero":
            code += f"print({helper['PYYAML_PROBE_SENTINEL']!r}, flush=True)\n"
        code += f"import os\nos._exit({0 if mode == 'zero-without-sentinel' else 7})\n"
    (tmp_path / "yaml.py").write_text(code)

    result = helper["_pyyaml_probe_succeeds"]((sys.executable, "-m", "pytest"), tmp_path)

    assert result is (mode == "healthy")
    assert marker.read_text() == "yaml-import"
    assert len(runtime_calls) == 1
    call = runtime_calls[0]
    assert call["command"] == (sys.executable, "-c", helper["PYYAML_PROBE_CODE"])
    assert call["cwd"] == tmp_path
    assert call["result"].returncode == (7 if mode == "nonzero" else 0)
    assert (helper["PYYAML_PROBE_SENTINEL"] in call["result"].stdout) is (
        mode != "zero-without-sentinel"
    )


def test_unrecognized_runtime_probe_never_launches_custom_command(tmp_path, helper, runtime_calls):
    marker = tmp_path / "must-not-run"
    command = (sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()")
    assert helper["_pyyaml_probe_succeeds"](command, tmp_path) is False
    assert runtime_calls == []
    assert not marker.exists()


def _failing_runtime(tmp_path, *, managed):
    marker = tmp_path / "executed"
    script = tmp_path / ("pytest.py" if managed else "custom.py")
    script.write_text(
        "import sys\nfrom pathlib import Path\n"
        f"with Path({str(marker)!r}).open('a') as stream: stream.write('original-command')\n"
        "print('File \"/private/runtime/yaml/parser.py\", line 1', file=sys.stderr)\n"
        "print('SyntaxError: broken private runtime', file=sys.stderr)\n"
        "raise SystemExit(1)\n"
    )
    command = (sys.executable, "-m", "pytest") if managed else (sys.executable, str(script))
    return command, marker


@pytest.mark.parametrize("managed", [False, True], ids=["custom", "managed"])
def test_real_missing_probe_executable_preserves_launch_cause(
    tmp_path, monkeypatch, helper, runtime_calls, managed
):
    command, marker = _failing_runtime(tmp_path, managed=managed)
    missing = tmp_path / "missing-probe"
    namespace = helper["_run_with_runtime_deps"].__globals__
    monkeypatch.setitem(namespace, "_pyyaml_probe_command", lambda *_: (str(missing),))
    monkeypatch.setitem(namespace, "_pyyaml_runtime_needs_repair", lambda: False)

    def forbidden_install():
        pytest.fail("a launch failure must not install dependencies")

    monkeypatch.setitem(namespace, "_ensure_pytest_runtime_deps", forbidden_install)
    with pytest.raises(helper["CommandUnavailableError"]) as caught:
        helper["_run_with_runtime_deps"](command, tmp_path)

    assert marker.read_text() == "original-command"
    assert isinstance(caught.value.error, FileNotFoundError)
    assert caught.value.__cause__ is caught.value.error
    assert caught.value.error.errno == errno.ENOENT
    assert caught.value.error.filename == str(missing)
    assert [(call["command"], call["cwd"]) for call in runtime_calls] == [
        (command, tmp_path),
        ((str(missing),), tmp_path),
    ]
    assert runtime_calls[0]["result"].returncode == 1
    assert caught.value.error is runtime_calls[1]["error"]


def test_repair_failure_preserves_dependency_error_without_rerunning(
    tmp_path, monkeypatch, helper, runtime_calls
):
    command, marker = _failing_runtime(tmp_path, managed=True)
    namespace = helper["_run_with_runtime_deps"].__globals__
    monkeypatch.setitem(namespace, "_pyyaml_runtime_needs_repair", lambda: True)
    original_error = OSError("private repair refused")
    repairs = []

    def failed_repair():
        repairs.append(marker.read_text())
        raise original_error

    monkeypatch.setitem(namespace, "_ensure_pytest_runtime_deps", failed_repair)
    with pytest.raises(helper["RuntimeDependencyError"]) as caught:
        helper["_run_with_runtime_deps"](command, tmp_path)

    assert repairs == ["original-command"]
    assert caught.value.error is original_error
    assert caught.value.__cause__ is original_error
    assert marker.read_text() == "original-command"
    assert [(call["command"], call["cwd"]) for call in runtime_calls] == [(command, tmp_path)]
    assert runtime_calls[0]["result"].returncode == 1
