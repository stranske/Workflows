"""Malformed pytest launchers cannot authorize a Python import probe or repair."""

import runpy
from pathlib import Path

import pytest


@pytest.fixture(params=["", "templates/consumer-repo/"], ids=["root", "template"])
def helper(request):
    root = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(root / request.param / "scripts/check_deliberate_break.py"))


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    """Use real PATH lookup, with no fallback to an installed Python or pytest."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    monkeypatch.setenv("PATH", str(bindir))
    path = bindir / "pytest"
    path.touch()
    path.chmod(0o755)
    return path


def assert_no_probe(helper, launcher):
    command = (str(launcher), "tests/test_named.py::test_named")
    assert helper["_pyyaml_probe_command"](command, launcher.parent) is None
    assert helper["_uses_pytest_runtime"](command) is False
    assert helper["_pyyaml_probe_succeeds"](command, launcher.parent) is False


def test_empty_pytest_launcher_has_no_probe(helper, launcher):
    assert_no_probe(helper, launcher)


def test_missing_shebang_has_no_probe(helper, launcher):
    launcher.write_text("print('not an interpreter declaration')\n", encoding="utf-8")
    assert_no_probe(helper, launcher)


def test_unclosed_shebang_quote_has_no_probe(helper, launcher):
    launcher.write_text("#!/usr/bin/env 'python\n", encoding="utf-8")
    assert_no_probe(helper, launcher)


def test_unresolved_env_python_has_no_probe(helper, launcher):
    launcher.write_text("#!/usr/bin/env -S python3 -I\n", encoding="utf-8")
    assert_no_probe(helper, launcher)
