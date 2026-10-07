"""Exercise real command launch boundaries in root and consumer proof helpers."""

import errno
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(params=["", "templates/consumer-repo/"], ids=["root", "template"])
def helper(request):
    root = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(root / request.param / "scripts/check_deliberate_break.py"))


def test_real_command_preserves_existing_pythonpath(tmp_path, monkeypatch, helper):
    prior_root = tmp_path / "prior-import-root"
    prior_root.mkdir()
    (prior_root / "launch_dependency.py").write_text("VALUE = 'inherited-import'\n")
    prior = str(prior_root)
    monkeypatch.setenv("PYTHONPATH", prior)
    command = (
        sys.executable,
        "-c",
        "import os, launch_dependency; print(os.environ['PYTHONPATH']); "
        "print(launch_dependency.VALUE)",
    )
    result = helper["_run"](command, tmp_path)
    assert result.returncode == 0
    assert result.stdout.splitlines() == [str(tmp_path) + os.pathsep + prior, "inherited-import"]
    assert result.stderr == ""
    assert os.environ["PYTHONPATH"] == prior


def test_missing_test_never_launches_the_command(tmp_path, helper):
    marker = tmp_path / "must-not-execute"
    command = (sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()")
    spec = helper["DeliberateBreakSpec"]("missing-test", "missing.py", "app.py", command)
    result = helper["verify_spec"](spec, base="irrelevant", cwd=tmp_path, enforce_tamper=False)
    assert result == {
        "verdict": "FAIL_BROKEN",
        "reason": "test-file-missing",
        "test_file": "missing.py",
    }
    assert not marker.exists()


def test_real_missing_executable_is_wrapped_with_its_cause(tmp_path, helper):
    command = (str(tmp_path / "nonexistent-command"),)
    with pytest.raises(helper["CommandUnavailableError"]) as caught:
        helper["_run_with_runtime_deps"](command, tmp_path)
    assert isinstance(caught.value.error, FileNotFoundError)
    assert caught.value.__cause__ is caught.value.error
    assert caught.value.error.errno == errno.ENOENT
    assert caught.value.error.filename == command[0]
    assert str(tmp_path / "nonexistent-command") in str(caught.value.error)


def _short_timeout(helper, monkeypatch):
    original = helper["_run"]

    def run(command, cwd):
        return original(command, cwd, timeout=0.25)

    monkeypatch.setitem(helper["_run_with_runtime_deps"].__globals__, "_run", run)


def test_real_head_timeout_stops_before_base_archive(tmp_path, monkeypatch, helper):
    (tmp_path / "test_proof.txt").write_text("proof")
    command = (sys.executable, "-c", "import time; time.sleep(10)")
    spec = helper["DeliberateBreakSpec"]("timeout-proof", "test_proof.txt", "app.py", command)
    _short_timeout(helper, monkeypatch)

    def forbidden_archive(*args):
        pytest.fail("a timed-out head must never reach base extraction")

    monkeypatch.setitem(helper["verify_spec"].__globals__, "_archive_ref", forbidden_archive)
    result = helper["verify_spec"](spec, base="unused", cwd=tmp_path, enforce_tamper=False)
    assert result == {
        "verdict": "FAIL_BROKEN",
        "reason": "command-timeout",
        "command": list(command),
        "timeout": 0.25,
    }


def test_real_base_timeout_is_broken_and_cleans_private_archive(tmp_path, monkeypatch, helper):
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in [
        ["init", "-q"],
        ["config", "user.name", "Launch Proof"],
        ["config", "user.email", "launch@example.com"],
    ]:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    (repo / "phase.txt").write_text("base")
    (repo / "test_proof.txt").write_text("proof")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True, capture_output=True)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    (repo / "phase.txt").write_text("head")
    (repo / "test_proof.txt").write_bytes(b"candidate proof\r\n")
    (repo / "untracked.bin").write_bytes(b"\x00\xffcandidate\r\n")
    candidate_bytes = {
        path.relative_to(repo): path.read_bytes()
        for path in repo.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(repo).parts
    }
    command = (
        sys.executable,
        "-c",
        "from pathlib import Path; import time; "
        "assert Path('test_proof.txt').read_bytes() == b'candidate proof\\r\\n'; "
        "time.sleep(10 if Path('phase.txt').read_text() == 'base' else 0)",
    )
    spec = helper["DeliberateBreakSpec"](
        "base-timeout-proof", "test_proof.txt", "phase.txt", command
    )
    _short_timeout(helper, monkeypatch)
    extracted = []
    original = helper["_archive_ref"]

    def archive(base, target, cwd):
        extracted.append(target)
        original(base, target, cwd)
        assert target != repo
        assert (target / "phase.txt").read_bytes() == b"base"
        assert (target / "test_proof.txt").read_bytes() == b"proof"
        assert not (target / "untracked.bin").exists()

    monkeypatch.setitem(helper["verify_spec"].__globals__, "_archive_ref", archive)
    result = helper["verify_spec"](spec, base=base, cwd=repo, enforce_tamper=False)
    assert result == {
        "verdict": "FAIL_BROKEN",
        "reason": "command-timeout",
        "command": list(command),
        "timeout": 0.25,
    }
    assert len(extracted) == 1
    assert not extracted[0].exists()
    assert {
        path.relative_to(repo): path.read_bytes()
        for path in repo.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(repo).parts
    } == candidate_bytes
