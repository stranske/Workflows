"""A successful repair must not conceal later launch or base-runtime failures."""

import errno
import runpy
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(params=["", "templates/consumer-repo/"], ids=["root", "template"])
def helper(request):
    root = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(root / request.param / "scripts/check_deliberate_break.py"))


@pytest.mark.parametrize("phase", ["probe", "rerun"])
def test_repaired_runtime_preserves_a_later_real_launch_failure(
    tmp_path, monkeypatch, helper, phase
):
    marker = tmp_path / "executions"
    launcher = tmp_path / "pytest"
    launcher.write_text(
        f"#!{sys.executable}\n"
        "import sys\nfrom pathlib import Path\n"
        f"with Path({str(marker)!r}).open('a') as stream: stream.write('original\\n')\n"
        "print(\"ModuleNotFoundError: No module named 'yaml'\", file=sys.stderr)\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    missing = tmp_path / "missing-probe" if phase == "probe" else launcher
    command = (str(launcher),)
    namespace = helper["_run_with_runtime_deps"].__globals__
    assert helper["_uses_pytest_runtime"](command)
    run = namespace["_run"]
    calls = []
    repairs = []

    def observed_run(argv, cwd):
        call = {"command": argv, "cwd": cwd}
        calls.append(call)
        try:
            call["result"] = run(argv, cwd)
        except OSError as error:
            call["error"] = error
            raise
        return call["result"]

    def repair():
        repairs.append(marker.read_text())
        # A private module supplies a real successful import, without installation.
        (tmp_path / "yaml.py").write_text("REPAIRED = True\n", encoding="utf-8")
        if phase == "rerun":
            launcher.unlink()

    probe = (
        (str(missing),) if phase == "probe" else (sys.executable, "-c", helper["PYYAML_PROBE_CODE"])
    )
    monkeypatch.setitem(namespace, "_run", observed_run)
    monkeypatch.setitem(namespace, "_ensure_pytest_runtime_deps", repair)
    monkeypatch.setitem(namespace, "_pyyaml_probe_command", lambda *_: probe)

    with pytest.raises(helper["CommandUnavailableError"]) as caught:
        helper["_run_with_runtime_deps"](command, tmp_path)

    assert repairs == ["original\n"]
    assert marker.read_text() == "original\n"
    assert isinstance(caught.value.error, FileNotFoundError)
    assert caught.value.__cause__ is caught.value.error
    assert caught.value.error.errno == errno.ENOENT
    assert caught.value.error.filename == str(missing)
    assert caught.value.error is calls[-1]["error"]
    assert calls[0]["result"].returncode == 1
    expected = [command, probe] + ([command] if phase == "rerun" else [])
    assert [(call["command"], call["cwd"]) for call in calls] == [
        (argv, tmp_path) for argv in expected
    ]
    if phase == "rerun":
        assert calls[1]["result"].returncode == 0
        assert helper["PYYAML_PROBE_SENTINEL"] in calls[1]["result"].stdout


def test_base_dependency_failure_keeps_its_cause_and_cleans_real_archive(
    tmp_path, monkeypatch, helper
):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.email", "proof@example.invalid")
    git("config", "user.name", "Runtime proof")
    (repo / "phase.txt").write_text("base", encoding="utf-8")
    (repo / "proof.txt").write_text("candidate test overlay\n", encoding="utf-8")
    (repo / "pytest.py").write_text(
        "from pathlib import Path\nimport sys\n"
        "if Path('phase.txt').read_text() == 'base':\n"
        "    print(\"ModuleNotFoundError: No module named 'yaml'\", file=sys.stderr)\n"
        "    raise SystemExit(1)\n",
        encoding="utf-8",
    )
    git("add", ".")
    git("commit", "-qm", "private base runtime")
    base = git("rev-parse", "HEAD")
    (repo / "phase.txt").write_text("head", encoding="utf-8")
    (repo / "proof.txt").write_text("updated candidate test overlay\n", encoding="utf-8")
    namespace = helper["verify_spec"].__globals__
    archive = namespace["_archive_ref"]
    run = namespace["_run"]
    dependency_result = namespace["_runtime_dependency_error_result"]
    archives = []
    repairs = []
    launches = []
    reported_errors = []
    cause = OSError("private wheel storage unavailable")
    dependency_error = ImportError("private dependency repair failed")

    def observed_archive(ref, target, cwd):
        archives.append(target)
        result = archive(ref, target, cwd)
        assert (target / "phase.txt").read_text() == "base"
        assert (target / "proof.txt").read_bytes() == b"candidate test overlay\n"
        return result

    def observed_run(argv, cwd):
        result = run(argv, cwd)
        if argv == command:
            launches.append((cwd, result.returncode))
        return result

    def observed_dependency_result(error):
        reported_errors.append(error)
        return dependency_result(error)

    def failed_repair():
        assert archives[0].is_dir()
        assert (archives[0] / "phase.txt").read_text() == "base"
        assert (archives[0] / "proof.txt").read_bytes() == b"updated candidate test overlay\n"
        repairs.append(True)
        raise dependency_error from cause

    monkeypatch.setitem(namespace, "_archive_ref", observed_archive)
    monkeypatch.setitem(namespace, "_run", observed_run)
    monkeypatch.setitem(namespace, "_runtime_dependency_error_result", observed_dependency_result)
    monkeypatch.setitem(namespace, "_ensure_pytest_runtime_deps", failed_repair)
    command = (sys.executable, "-m", "pytest")
    spec = helper["DeliberateBreakSpec"]("repair-proof", "proof.txt", "phase.txt", command)

    result = helper["verify_spec"](spec, base=base, cwd=repo, enforce_tamper=False)

    assert result == {
        "verdict": "FAIL_BROKEN",
        "reason": "dependency-import-failed",
        "detail": "private dependency repair failed",
        "cause": "private wheel storage unavailable",
    }
    assert repairs == [True]
    assert reported_errors == [dependency_error]
    assert reported_errors[0] is dependency_error
    assert dependency_error.__cause__ is cause
    assert len(archives) == 1
    assert launches == [(repo, 0), (archives[0], 1)]
    assert not archives[0].exists()
    assert (repo / "phase.txt").read_text() == "head"
    assert (repo / "proof.txt").read_bytes() == b"updated candidate test overlay\n"
