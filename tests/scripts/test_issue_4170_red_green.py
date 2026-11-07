"""Regression tests for issue #4170 validate-red-green production restoration."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/evidence/issue-4170/validate-red-green.py"


def _load_validate_module() -> object:
    spec = importlib.util.spec_from_file_location("validate_red_green_issue_4170", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def isolated_validate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mod = _load_validate_module()
    fake_repo = tmp_path / "repo"
    fake_out = tmp_path / "out"
    fake_out.mkdir()
    case = mod.CASES[0]
    prod = fake_repo / case.rel_path
    prod.parent.mkdir(parents=True)
    original_text = f"# stub\n{case.old}\n"
    prod.write_text(original_text, encoding="utf-8")
    original_bytes = prod.read_bytes()

    mod.REPO = fake_repo
    mod.OUT_DIR = fake_out
    mod.CASES = (case,)

    def green_suite_run(cmd, **kwargs):
        if mod.TARGET_TESTS[0] in cmd and mod.TARGET_TESTS[-1] in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="112 passed\n", stderr="")
        raise AssertionError(f"unexpected subprocess.run: {cmd!r}")

    monkeypatch.setattr(mod.subprocess, "run", green_suite_run)
    return mod, prod, original_bytes, case


def test_restores_after_keyboard_interrupt_during_red_pytest(
    isolated_validate, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod, prod, original_bytes, _case = isolated_validate

    def run_exact(_nodeid: str) -> subprocess.CompletedProcess[str]:
        raise KeyboardInterrupt()

    monkeypatch.setattr(mod, "run_pytest_exact", run_exact)
    with pytest.raises(KeyboardInterrupt):
        mod.main()
    assert prod.read_bytes() == original_bytes


def test_restores_after_subprocess_error_during_red_pytest(
    isolated_validate, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod, prod, original_bytes, _case = isolated_validate

    def run_exact(_nodeid: str) -> subprocess.CompletedProcess[str]:
        raise subprocess.SubprocessError("mock subprocess failure")

    monkeypatch.setattr(mod, "run_pytest_exact", run_exact)
    with pytest.raises(subprocess.SubprocessError):
        mod.main()
    assert prod.read_bytes() == original_bytes


def test_restores_after_red_log_write_oserror(
    isolated_validate, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod, prod, original_bytes, case = isolated_validate
    original_write_text = Path.write_text

    def run_exact(_nodeid: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 1, stdout="FAILED\n", stderr="")

    def write_text(self: Path, *args, **kwargs):
        if self.parent.name == "red" and self.name == f"{case.nodeid_suffix}.log":
            raise OSError("mock red log write failure")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(mod, "run_pytest_exact", run_exact)
    monkeypatch.setattr(Path, "write_text", write_text)
    with pytest.raises(OSError, match="mock red log write failure"):
        mod.main()
    assert prod.read_bytes() == original_bytes
