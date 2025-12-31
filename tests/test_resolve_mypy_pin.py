from __future__ import annotations

import builtins
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import resolve_mypy_pin


def _write_pyproject(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_get_mypy_python_version_returns_none_without_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert resolve_mypy_pin.get_mypy_python_version() is None


def test_get_mypy_python_version_uses_tomlkit_when_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path / "pyproject.toml",
        """
[tool.mypy]
python_version = "3.9"
""",
    )

    fake_module = SimpleNamespace(
        parse=lambda content: {"tool": {"mypy": {"python_version": "3.8"}}}
    )
    monkeypatch.setitem(sys.modules, "tomlkit", fake_module)

    assert resolve_mypy_pin.get_mypy_python_version() == "3.8"


def test_get_mypy_python_version_falls_back_to_regex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path / "pyproject.toml",
        """
[tool.mypy]
python_version = "3.10"
""",
    )

    original_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "tomlkit":
            raise ImportError("tomlkit not available")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert resolve_mypy_pin.get_mypy_python_version() == "3.10"


def test_main_writes_github_output_from_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path / "pyproject.toml",
        """
[tool.mypy]
python_version = "3.7"
""",
    )
    output_path = tmp_path / "output.txt"

    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    monkeypatch.setenv("MATRIX_PYTHON_VERSION", "3.12")

    assert resolve_mypy_pin.main() == 0
    assert output_path.read_text(encoding="utf-8") == "python-version=3.7\n"


def test_main_defaults_to_matrix_or_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = tmp_path / "output.txt"

    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    monkeypatch.setenv("MATRIX_PYTHON_VERSION", "3.9")

    assert resolve_mypy_pin.main() == 0
    assert output_path.read_text(encoding="utf-8") == "python-version=3.9\n"
