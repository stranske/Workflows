"""Validation setup must fail before collection when its runtime is incomplete."""

from __future__ import annotations

import subprocess
import sys

import pytest
from scripts import setup_validation_env as setup


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.13"\n'
        'dependencies = ["defusedxml==0.7.1"]\n'
        '[project.optional-dependencies]\ndev = ["mypy==2.4.1", "pytest==9.2.0"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(setup, "ROOT", tmp_path)
    monkeypatch.setattr(setup.sys, "version_info", (3, 13, 0))
    return tmp_path


@pytest.mark.parametrize("reuse", (False, True))
def test_provision_installs_declared_dependencies_and_checks_imports(project, monkeypatch, reuse):
    calls = []
    monkeypatch.setattr(setup.subprocess, "run", lambda argv, **kw: calls.append((argv, kw)))
    python = setup.provision(project / "env with spaces", system_site_packages=reuse)

    assert calls[0] == (
        [
            sys.executable,
            "-m",
            "venv",
            *(["--system-site-packages"] if reuse else []),
            str(python.parent.parent),
        ],
        {"check": True},
    )
    assert calls[1] == (
        [str(python), "-m", "pip", "install", "defusedxml==0.7.1", "mypy==2.4.1", "pytest==9.2.0"],
        {"check": True},
    )
    assert calls[2] == ([str(python), "-c", setup.IMPORT_CHECK], {"check": True})


def test_unsupported_python_fails_before_creating_environment(project, monkeypatch):
    monkeypatch.setattr(setup.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(setup.subprocess, "run", lambda *a, **kw: pytest.fail("Must reject first"))
    with pytest.raises(ValueError, match="Python >=3.13 required"):
        setup.provision(project / "env")


@pytest.mark.parametrize("failed_step", (0, 1, 2))
def test_setup_failure_cannot_report_ready(project, monkeypatch, capsys, failed_step):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        if len(calls) == failed_step + 1:
            raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(setup.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["setup_validation_env.py", str(project / "env")])
    assert setup.main() == 1
    assert len(calls) == failed_step + 1
    output = capsys.readouterr()
    assert "setup failed" in output.err
    assert "Environment ready" not in output.out
