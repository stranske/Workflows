"""Exit-code and restoration contract for the retained mutation proofs."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[2] / "docs/evidence/issue-4170/run_break_and_revert.py"
spec = importlib.util.spec_from_file_location("issue_4170_runner", RUNNER)
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


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

    def red(node):
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

    def run(node):
        calls.append(node)
        if failure == "red_exception" or (failure == "green_exception" and len(calls) == 2):
            raise RuntimeError("subprocess failed")
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


def test_records_only_test_failure_then_success(isolated_runner, monkeypatch):
    target, original, manifest = isolated_runner
    results = iter(
        [
            subprocess.CompletedProcess([], 1, "1 failed", ""),
            subprocess.CompletedProcess([], 0, "1 passed", ""),
        ]
    )
    monkeypatch.setattr(runner, "run_pytest", lambda node: next(results))
    assert runner.main() == 0
    assert target.read_bytes() == original
    assert manifest.exists()
