"""Protect source restoration and interpreter selection in the r3 evidence driver."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

DRIVER = Path(__file__).resolve().parents[2] / "docs/evidence/issue-4019/r3/mutate.py"


def load_driver():
    spec = importlib.util.spec_from_file_location("issue_4019_mutation_driver", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_partial_write_restores_original(tmp_path, monkeypatch):
    driver = load_driver()
    source = tmp_path / "source.py"
    original = b"original = True\n"
    source.write_bytes(original)
    monkeypatch.setattr(
        driver, "MUTATIONS", [("injected", "unused", str(source), "True", "False", 1)]
    )

    def partial_write(path, text):
        path.write_bytes(b"partial")
        raise OSError("injected partial write")

    monkeypatch.setattr(Path, "write_text", partial_write)
    with pytest.raises(OSError, match="injected partial write"):
        driver.main(tmp_path)
    assert source.read_bytes() == original


def test_subprocess_uses_active_interpreter(monkeypatch):
    # Use a distinct value so a hardcoded path cannot pass by coincidence.
    active = "/selected/environment/bin/python"
    monkeypatch.setattr(sys, "executable", active)
    driver = load_driver()
    calls = []

    def subprocess_run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="passed\n", stderr="")

    monkeypatch.setattr(driver.subprocess, "run", subprocess_run)
    assert driver.run("test.py::test_case") == (0, "passed\n")
    assert calls == [[active, "-m", "pytest", "test.py::test_case", "-q", "-p", "no:cacheprovider"]]
