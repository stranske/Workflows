"""Canonical lock declarations for non-package consumers, without mutation/install."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = [
    "scripts/sync_test_dependencies.py",
    "templates/consumer-repo/scripts/sync_test_dependencies.py",
]


@pytest.fixture(params=SCRIPTS)
def auditor(request, tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("lock_auditor", ROOT / request.param)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "PYPROJECT_FILE", tmp_path / "pyproject.toml")
    monkeypatch.setattr(module, "LOCAL_MODULES_FILE", tmp_path / ".project_modules.txt")
    return module


def nonpackage(tmp_path, *, imports="pydantic", pins="pydantic==2.13.4\n"):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npythonpath=["src", "tests"]\n'
    )
    (tmp_path / "requirements.lock").write_text(pins)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_contract.py").write_text(f"import {imports}\n")
    return {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_actual_nonpackage_verify_and_fix_use_declared_pin_without_tomlkit(
    auditor, tmp_path, monkeypatch
):
    before = nonpackage(tmp_path)
    monkeypatch.setattr(auditor, "TOMLKIT_ERROR", ImportError("not installed"))
    declared, groups = auditor.get_declared_dependencies()
    assert declared == {"pydantic"}
    assert groups == {"requirements.lock": ["pydantic==2.13.4"]}
    assert auditor.main(["--verify"]) == 0
    assert auditor.main(["--fix"]) == 0
    assert {p: p.read_bytes() for p in before} == before


def test_nonpackage_unlisted_import_still_fails_and_fix_never_creates_project(
    auditor, tmp_path, monkeypatch
):
    before = nonpackage(tmp_path, imports="not_declared_package")
    monkeypatch.setattr(auditor, "TOMLKIT_ERROR", ImportError("not installed"))
    assert auditor.main(["--verify"]) == 1
    with pytest.raises(SystemExit, match="non-package.*requirements.lock"):
        auditor.main(["--fix"])
    assert {p: p.read_bytes() for p in before} == before
    assert "[project]" not in (tmp_path / "pyproject.toml").read_text()


def test_no_pyproject_lock_is_supported_without_creating_one(auditor, tmp_path):
    (tmp_path / "requirements.lock").write_text("pydantic==2.13.4\n")
    assert auditor.get_declared_dependencies()[0] == {"pydantic"}
    assert not (tmp_path / "pyproject.toml").exists()


def test_project_declarations_remain_authoritative_and_ignore_lock(auditor, tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies=["requests>=2"]\n[project.optional-dependencies]\ndev=["PyYAML>=6"]\n'
    )
    (tmp_path / "requirements.lock").write_text("pydantic==2.13.4\n-r unsafe.in\n")
    assert auditor.get_declared_dependencies() == (
        {"requests", "pyyaml"},
        {"dependencies": ["requests>=2"], "dev": ["PyYAML>=6"]},
    )


def test_empty_project_table_does_not_enable_lock_fallback(auditor, tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "requirements.lock").write_text("pydantic==2.13.4\n")
    assert auditor.get_declared_dependencies() == (set(), {})


def test_lock_is_same_config_root_not_current_directory(auditor, tmp_path, monkeypatch):
    root = tmp_path / "configuration"
    root.mkdir()
    config = root / "pyproject.toml"
    config.write_text("[tool.ruff]\n")
    (root / "requirements.lock").write_text("PyYAML==6.0.3\n")
    (tmp_path / "requirements.lock").write_text("pydantic==2.13.4\n")
    monkeypatch.setattr(auditor, "PYPROJECT_FILE", config)
    assert auditor.get_declared_dependencies()[0] == {"pyyaml"}


@pytest.mark.parametrize(
    "line",
    [
        "-r requirements.in",
        "--requirement other.lock",
        "-e .",
        "--extra-index-url https://example.invalid",
        "pkg @ https://example.invalid/pkg.whl",
        "https://example.invalid/pydantic.whl",
        "pydantic>=2",
        "pydantic==2.*",
        "pydantic===2.13.4",
        'pydantic==2.13.4; python_version<"3.0"',
        "pydantic[extra]==2.13.4",
        "pydantic==${VERSION}",
        "pydantic==banana",
        "pydantic==2.13.4 --hash=sha256:abcd",
        "pydantic==2.13.4 \\",
    ],
)
def test_unsafe_or_unsupported_lock_line_cannot_declare_import(auditor, tmp_path, line, capsys):
    before = nonpackage(tmp_path, pins=f"pydantic==2.13.4\n{line}\n")
    assert auditor.main(["--verify"]) == 2
    assert "requirements.lock:2" in capsys.readouterr().err
    assert {p: p.read_bytes() for p in before} == before


def test_comments_blank_lines_and_normalized_names_are_supported(auditor, tmp_path):
    nonpackage(
        tmp_path, imports="yaml", pins="# generated pins\n\nPyYAML==6.0.3\npython-docx==1.2.0\n"
    )
    assert auditor.find_missing_dependencies() == set()
    assert auditor.get_declared_dependencies()[0] == {"pyyaml", "python_docx"}


def test_actual_consumer_five_pin_lock_covers_imports_without_package_conversion(
    auditor, tmp_path, monkeypatch
):
    # Exact declaration shape retained from the failing Orchestrator revision;
    # parsing imports does not import/install any of these libraries.
    pins = (
        "PyYAML==6.0.3\nrequests==2.34.2\njsonschema==4.26.0\npsutil==7.2.2\n"
        "# Test-only: exercise retained native LLMUsage/LLMChunk validation without SDK imports.\n"
        "pydantic==2.13.4\n"
    )
    before = nonpackage(tmp_path, pins=pins)
    test_file = tmp_path / "tests/test_contract.py"
    test_file.write_text("import yaml, requests, jsonschema, psutil, pydantic\n")
    before[test_file] = test_file.read_bytes()
    monkeypatch.setattr(auditor, "TOMLKIT_ERROR", ImportError("not installed"))
    assert auditor.find_missing_dependencies() == set()
    assert auditor.main(["--verify"]) == 0
    assert auditor.main(["--fix"]) == 0
    assert {path: path.read_bytes() for path in before} == before


def test_project_unlisted_import_cannot_be_hidden_by_installed_lock(auditor, tmp_path):
    nonpackage(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies=["requests>=2"]\n')
    assert auditor.find_missing_dependencies() == {"pydantic"}
    assert auditor.main(["--verify"]) == 1
