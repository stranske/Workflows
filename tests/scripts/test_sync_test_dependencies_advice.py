"""Audit advice follows the real declaration kind without installing or mutating."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(
    params=[
        "scripts/sync_test_dependencies.py",
        "templates/consumer-repo/scripts/sync_test_dependencies.py",
    ]
)
def auditor(request, tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("advice_auditor", ROOT / request.param)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "PYPROJECT_FILE", tmp_path / "pyproject.toml")
    monkeypatch.setattr(module, "LOCAL_MODULES_FILE", tmp_path / ".project_modules.txt")
    monkeypatch.setattr(module, "TOMLKIT_ERROR", ImportError("not installed"))
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_contract.py").write_text("import pydantic\n")
    return module


@pytest.mark.parametrize("argv,code", [([], 0), (["--verify"], 1)])
@pytest.mark.parametrize("config", [None, '[tool.pytest.ini_options]\npythonpath=["src"]\n'])
def test_nonpackage_missing_dependency_advice_is_actionable_without_fix(
    auditor, tmp_path, capsys, argv, code, config
):
    if config is not None:
        (tmp_path / "pyproject.toml").write_text(config)
    (tmp_path / "requirements.lock").write_text("# pydantic is not declared\n")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert auditor.main(argv) == code
    output = capsys.readouterr().out
    assert "pydantic" in output
    assert "requirements.lock" in output
    assert "python -m pip install -r requirements.lock" in output
    assert "tests" in output and "audit" in output
    assert "--fix" not in output and "optional-dependencies" not in output
    assert {p: p.read_bytes() for p in before} == before
    assert (
        not auditor.PYPROJECT_FILE.exists()
        if config is None
        else "[project]" not in auditor.PYPROJECT_FILE.read_text()
    )


@pytest.mark.parametrize("argv,code", [([], 0), (["--verify"], 1)])
def test_packaged_missing_dependency_keeps_original_fix_advice(
    auditor, tmp_path, capsys, argv, code
):
    config = '[project]\nname="fixture-package"\ndependencies=[]\n'
    auditor.PYPROJECT_FILE.write_text(config)
    assert auditor.main(argv) == code
    output = capsys.readouterr().out
    assert "pydantic" in output
    assert "python scripts/sync_test_dependencies.py --fix" in output
    assert "requirements.lock" not in output
    assert auditor.PYPROJECT_FILE.read_text() == config
