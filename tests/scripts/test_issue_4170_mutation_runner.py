"""Exit-code and restoration contract for the retained mutation proofs."""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[2] / "docs/evidence/issue-4170/run_break_and_revert.py"
spec = importlib.util.spec_from_file_location("issue_4170_runner", RUNNER)
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


def _red_junit(*, failures: int = 1, errors: int = 0) -> str:
    cases = []
    for _ in range(failures):
        cases.append(
            '  <testcase classname="production" name="test_node">\n'
            '    <failure message="assert">failed</failure>\n'
            "  </testcase>\n"
        )
    for _ in range(errors):
        cases.append(
            '  <testcase classname="production" name="test_node">\n'
            '    <error message="setup">setup failed</error>\n'
            "  </testcase>\n"
        )
    if not cases:
        cases.append('  <testcase classname="production" name="test_node"/>\n')
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<testsuite tests="{len(cases)}" failures="{failures}" errors="{errors}">\n'
        + "".join(cases)
        + "</testsuite>\n"
    )


@pytest.fixture
def isolated_runner(tmp_path, monkeypatch):
    target = tmp_path / "production.py"
    original = b"original = True\n"
    target.write_bytes(original)
    mutation = runner.Mutation("test_node", "production.py", "fixture", "True", "False")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "EVIDENCE", tmp_path)
    monkeypatch.setattr(runner, "MUTATIONS", [mutation])
    return target, original, tmp_path / "break-and-revert-manifest.json"


@pytest.mark.parametrize("exit_code", [0, 2, 3, 4, 5])
def test_rejects_non_failure_exit_and_restores(isolated_runner, monkeypatch, exit_code):
    target, original, manifest = isolated_runner
    calls = []

    def red(node, junit_path=None):
        calls.append(node)
        assert target.read_text() == "original = False\n"
        return subprocess.CompletedProcess([], exit_code, "", "")

    monkeypatch.setattr(runner, "run_pytest", red)
    with pytest.raises(
        RuntimeError, match=f"expected pytest exit 1 under mutation, got {exit_code}"
    ):
        runner.main()
    assert target.read_bytes() == original
    assert len(calls) == 1
    assert not manifest.exists()


@pytest.mark.parametrize(
    "failure", ["red_exception", "green_exception", "green_failure", "restore_exception"]
)
def test_restores_on_other_failures(isolated_runner, monkeypatch, failure):
    target, original, manifest = isolated_runner
    calls = []

    def run(node, junit_path=None):
        calls.append(node)
        if failure == "red_exception" or (failure == "green_exception" and len(calls) == 2):
            raise RuntimeError("subprocess failed")
        if junit_path is not None:
            junit_path.write_text(_red_junit(), encoding="utf-8")
        return subprocess.CompletedProcess([], 1, "1 failed", "")

    monkeypatch.setattr(runner, "run_pytest", run)
    if failure == "restore_exception":

        def broken_restore(*args):
            raise RuntimeError("restore failed")

        monkeypatch.setattr(runner, "restore_patch", broken_restore)
    with pytest.raises(RuntimeError):
        runner.main()
    assert target.read_bytes() == original
    assert not manifest.exists()


@pytest.mark.parametrize(
    "failures,errors,match",
    [
        (0, 1, "exactly one test failure and zero errors"),
        (0, 0, "exactly one test failure and zero errors"),
        (2, 0, "exactly one test failure and zero errors"),
    ],
)
def test_rejects_red_junit_without_single_test_failure(
    isolated_runner, monkeypatch, failures, errors, match
):
    target, original, manifest = isolated_runner

    def red(node, junit_path=None):
        if junit_path is None:
            return subprocess.CompletedProcess([], 0, "1 passed", "")
        junit_path.write_text(_red_junit(failures=failures, errors=errors), encoding="utf-8")
        return subprocess.CompletedProcess([], 1, "1 failed", "")

    monkeypatch.setattr(runner, "run_pytest", red)
    with pytest.raises(RuntimeError, match=match):
        runner.main()
    assert target.read_bytes() == original
    assert not manifest.exists()


def test_records_only_test_failure_then_success(isolated_runner, monkeypatch):
    target, original, manifest = isolated_runner
    results = iter(
        [
            subprocess.CompletedProcess([], 1, "1 failed", ""),
            subprocess.CompletedProcess([], 0, "1 passed", ""),
        ]
    )

    def run(node, junit_path=None):
        proc = next(results)
        if proc.returncode == 1 and junit_path is not None:
            junit_path.write_text(_red_junit(), encoding="utf-8")
        return proc

    monkeypatch.setattr(runner, "run_pytest", run)
    assert runner.main() == 0
    assert target.read_bytes() == original
    assert manifest.exists()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    proof = data["proofs"][0]
    assert proof["node_id"] == "test_node"
    assert proof["red_exit"] == 1
    assert proof["green_exit"] == 0
    expected_hash = hashlib.sha256(original).hexdigest()
    assert data["restored_production_sha256"]["production.py"] == expected_hash


def test_subprocess_cache_isolation_with_real_execution(tmp_path, monkeypatch):
    """Real subprocess regression: mutant bytecode cannot be read or reused."""
    target = tmp_path / "test_real_module.py"
    original_content = "def test_real_pass():\n    assert True\n"
    target.write_text(original_content)

    mutant_content = "def test_real_pass():\n    assert False\n"
    equal_length_mutant = mutant_content
    assert len(equal_length_mutant) == len(original_content) + 1
    equal_length_mutant = mutant_content[:-1]
    assert len(equal_length_mutant) == len(original_content)

    mutation = runner.Mutation(
        "test_real_module.py::test_real_pass",
        "test_real_module.py",
        "real subprocess cache isolation",
        original_content,
        equal_length_mutant,
    )

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "EVIDENCE", tmp_path)
    monkeypatch.setattr(runner, "MUTATIONS", [mutation])

    original_hash = hashlib.sha256(target.read_bytes()).hexdigest()

    result = runner.main()

    assert result == 0

    restored_content = target.read_text()
    assert restored_content == original_content

    restored_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    assert restored_hash == original_hash

    manifest = tmp_path / "break-and-revert-manifest.json"
    assert manifest.exists()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert len(data["proofs"]) == 1
    proof = data["proofs"][0]
    assert proof["red_exit"] == 1
    assert proof["green_exit"] == 0


def test_subprocess_identical_timestamps_and_sizes(tmp_path, monkeypatch):
    """Real subprocess regression with equal-length content and identical timestamps."""
    target = tmp_path / "test_timestamp.py"
    original_content = "def test_timestamp_value():\n    x = 1\n    assert x == 1\n"
    target.write_text(original_content)

    original_stat = target.stat()
    original_size = original_stat.st_size
    pinned_ns = (original_stat.st_atime_ns, original_stat.st_mtime_ns)

    mutant_content = "def test_timestamp_value():\n    x = 0\n    assert x == 1\n"
    equal_length_mutant = mutant_content
    assert len(equal_length_mutant) == original_size

    mutation = runner.Mutation(
        "test_timestamp.py::test_timestamp_value",
        "test_timestamp.py",
        "timestamp and size isolation",
        original_content,
        equal_length_mutant,
    )

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "EVIDENCE", tmp_path)
    monkeypatch.setattr(runner, "MUTATIONS", [mutation])

    observed = []
    real_apply = runner.apply_patch
    real_restore = runner.restore_patch
    real_run = runner.run_pytest

    def pinned_apply(path, before, after):
        real_apply(path, before, after)
        os.utime(path, ns=pinned_ns)

    def pinned_restore(path, before, after):
        real_restore(path, before, after)
        os.utime(path, ns=pinned_ns)

    def observing_run(node_id, *, junit_path=None):
        stat = target.stat()
        observed.append((stat.st_size, stat.st_mtime_ns))
        return real_run(node_id, junit_path=junit_path)

    monkeypatch.setattr(runner, "apply_patch", pinned_apply)
    monkeypatch.setattr(runner, "restore_patch", pinned_restore)
    monkeypatch.setattr(runner, "run_pytest", observing_run)

    result = runner.main()

    assert result == 0
    # Mutant (red) and restored (green) runs saw identical size and mtime, so only
    # per-run bytecode cache isolation lets the green run pass.
    assert observed == [
        (original_size, original_stat.st_mtime_ns),
        (original_size, original_stat.st_mtime_ns),
    ]
    data = json.loads((tmp_path / "break-and-revert-manifest.json").read_text(encoding="utf-8"))
    assert data["proofs"][0]["red_exit"] == 1
    assert data["proofs"][0]["green_exit"] == 0

    restored_stat = target.stat()
    assert restored_stat.st_size == original_size
    assert target.read_text() == original_content


def test_no_reusable_mutant_cache_after_failure_cleanup(tmp_path, monkeypatch):
    """Verify failure cleanup leaves no reusable mutant cache."""
    target = tmp_path / "test_cache_cleanup.py"
    original_content = "def test_cache_ok():\n    assert 1\n"
    target.write_text(original_content)

    equal_length_mutant = "def test_cache_ok():\n    assert 0\n"
    assert len(equal_length_mutant) == len(original_content)
    compile(equal_length_mutant, "test_cache_cleanup.py", "exec")

    mutation = runner.Mutation(
        "test_cache_cleanup.py::test_cache_ok",
        "test_cache_cleanup.py",
        "no reusable cache after cleanup",
        original_content,
        equal_length_mutant,
    )

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "EVIDENCE", tmp_path)
    monkeypatch.setattr(runner, "MUTATIONS", [mutation])

    result = runner.main()

    assert result == 0

    cache_dirs = list(tmp_path.rglob("*"))
    cache_dirs = [d for d in cache_dirs if d.is_dir() and "__pycache__" in str(d)]
    assert len(cache_dirs) == 0


def test_run_pytest_removes_cache_dir_when_subprocess_raises(isolated_runner, monkeypatch):
    target, original, manifest = isolated_runner
    recorded = []

    def raising_run(cmd, **kwargs):
        prefix = Path(kwargs["env"]["PYTHONPYCACHEPREFIX"])
        assert prefix.is_dir()
        recorded.append(prefix)
        assert target.read_text() == "original = False\n"
        raise OSError("subprocess launch failed")

    monkeypatch.setattr(runner.subprocess, "run", raising_run)
    with pytest.raises(OSError, match="subprocess launch failed"):
        runner.main()
    assert len(recorded) == 1
    assert not recorded[0].exists()
    assert target.read_bytes() == original
    assert not manifest.exists()


def test_run_pytest_removes_cache_dirs_after_successful_subprocess(isolated_runner, monkeypatch):
    target, original, manifest = isolated_runner
    recorded = []

    def fake_run(cmd, **kwargs):
        prefix = Path(kwargs["env"]["PYTHONPYCACHEPREFIX"])
        assert prefix.is_dir()
        recorded.append(prefix)
        junit = [arg for arg in cmd if arg.startswith("--junitxml=")]
        if junit:
            Path(junit[0].split("=", 1)[1]).write_text(_red_junit(), encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 1, "1 failed", "")
        return subprocess.CompletedProcess(cmd, 0, "1 passed", "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    assert runner.main() == 0
    assert len(recorded) == 2
    assert recorded[0] != recorded[1]
    assert not any(prefix.exists() for prefix in recorded)
    assert target.read_bytes() == original
    assert manifest.exists()
