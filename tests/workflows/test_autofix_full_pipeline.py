from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

import scripts.auto_type_hygiene as auto_type_hygiene
import scripts.mypy_autofix as mypy_autofix


def _run(
    cmd: list[str],
    cwd: Path,
    *,
    ok_exit_codes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode not in ok_exit_codes:
        raise AssertionError(
            f"Command failed: {' '.join(cmd)}\nReturn code: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


@pytest.mark.integration
def test_autofix_pipeline_resolves_lint_and_typing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the full autofix toolchain on a synthetic module."""

    for module in ("ruff", "isort", "docformatter", "black", "mypy"):
        pytest.importorskip(module)

    src_dir = tmp_path / "src"
    tests_dir = tmp_path / "tests"
    src_dir.mkdir()
    tests_dir.mkdir()

    sample = src_dir / "autofix_target.py"
    sample.write_text(
        dedent(
            '''
            import yaml
            import os


            def messy_function(a:int,b:int)->int:
                """Bad docstring spacing.   The docstring should be reformatted to follow conventions.
                Extra indentation should be removed."""
                if a>b:
                    return  yaml.safe_load("[]")
                return a +b


            def needs_optional(value: Optional[int])->int:
                if value is None:
                    return 0
                return value
            '''
        ).lstrip()
        + "\n",
        encoding="utf-8",
    )

    # Ruff should detect the style issues before fixes are applied.
    initial_ruff = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(sample)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert initial_ruff.returncode != 0, "Expected initial ruff check to fail"

    # Mypy should report the missing Optional import prior to autofix.
    initial_mypy = subprocess.run(
        [sys.executable, "-m", "mypy", "--ignore-missing-imports", str(sample)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert initial_mypy.returncode != 0, "Expected mypy to fail before autofix"
    assert "Optional" in (initial_mypy.stderr + initial_mypy.stdout)

    commands: list[tuple[list[str], tuple[int, ...]]] = [
        (
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--fix",
                "--exit-zero",
                str(sample),
            ],
            (0,),
        ),
        ([sys.executable, "-m", "isort", str(sample)], (0,)),
        ([sys.executable, "-m", "docformatter", "-i", str(sample)], (0, 3)),
        ([sys.executable, "-m", "black", str(sample)], (0,)),
        (
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--fix",
                "--exit-zero",
                str(sample),
            ],
            (0,),
        ),
    ]
    for cmd, ok_codes in commands:
        _run(cmd, cwd=tmp_path, ok_exit_codes=ok_codes)

    # Auto-type hygiene should attach import-untyped ignore comments to yaml.
    monkeypatch.setattr(auto_type_hygiene, "ROOT", tmp_path, raising=False)
    monkeypatch.setattr(auto_type_hygiene, "SRC_DIRS", [src_dir], raising=False)
    monkeypatch.setattr(auto_type_hygiene, "DRY_RUN", False, raising=False)
    monkeypatch.setenv("AUTO_TYPE_ALLOWLIST", "yaml")
    monkeypatch.setattr(auto_type_hygiene, "ALLOWLIST", ["yaml"], raising=False)
    auto_type_hygiene.main()

    # Mypy autofix should inject missing typing imports and normalise code again.
    monkeypatch.setattr(mypy_autofix, "ROOT", tmp_path, raising=False)
    monkeypatch.setattr(
        mypy_autofix,
        "DEFAULT_TARGETS",
        [src_dir, tests_dir],
        raising=False,
    )
    exit_code = mypy_autofix.main(["--paths", str(sample)])
    assert exit_code == 0

    for cmd in (
        [sys.executable, "-m", "isort", str(sample)],
        [sys.executable, "-m", "black", str(sample)],
        [sys.executable, "-m", "ruff", "check", "--fix", "--exit-zero", str(sample)],
    ):
        _run(cmd, cwd=tmp_path)

    _run([sys.executable, "-m", "ruff", "check", str(sample)], cwd=tmp_path)
    _run([sys.executable, "-m", "black", "--check", str(sample)], cwd=tmp_path)
    _run(
        [sys.executable, "-m", "mypy", "--ignore-missing-imports", str(sample)],
        cwd=tmp_path,
    )

    content = sample.read_text(encoding="utf-8")
    assert "from typing import Optional" in content
    assert "type: ignore" not in content
    assert "if a > b" in content
    assert "return a + b" in content
    assert '"""Bad docstring spacing.\n\n' in content
